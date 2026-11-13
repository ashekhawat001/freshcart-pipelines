"""FreshCart ELT pipeline.

    python run_pipeline.py --setup --mock    # first time: create objects, run on sample data
    python run_pipeline.py --mock            # run again on sample data (idempotent)
    python run_pipeline.py                   # real APIs from .env
    python run_pipeline.py --dry-run --mock  # extract only, no Snowflake needed

Order of work (each step needs the previous one):
  1 EXTRACT  APIs -> local landing files (raw JSON)
  2 LOAD     landing files -> Snowflake bronze tables (PUT + COPY INTO)
  3 TRANSFORM in Snowflake with SQL:
       10 cleanse orders -> 20 deduplicate -> (look up new pincodes) ->
       30 customers SCD2, 31 FX daily, 32 pincode geo -> 40 enrich + publish gold
  4 CHECK    data-quality assertions, then print the gold totals
"""
import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

import extract

SQL = Path(__file__).parent / "sql"
log = logging.getLogger("pipeline")


def parse_args():
    p = argparse.ArgumentParser(description="FreshCart ELT pipeline")
    p.add_argument("--setup", action="store_true", help="run sql/00_setup.sql first")
    p.add_argument("--mock", action="store_true", help="use built-in sample API responses")
    p.add_argument("--run-date", help="logical date YYYY-MM-DD (default: today)")
    p.add_argument("--dry-run", action="store_true", help="extract only; do not touch Snowflake")
    p.add_argument("--strict", action="store_true", help="fail (not warn) on quality warnings")
    return p.parse_args()


class Run:
    """Logs each step to the console and to ops.run_log, with timing."""
    def __init__(self, conn, run_id):
        self.conn, self.run_id = conn, run_id

    def record(self, step, status, detail=""):
        if self.conn is None:
            return
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO ops.run_log (run_id, step, status, detail) VALUES (%s, %s, %s, %s)",
                        (self.run_id, step, status, str(detail)[:4000]))

    def step(self, name, fn, *a, **kw):
        t0 = time.time()
        log.info("▶ %s", name)
        try:
            out = fn(*a, **kw)
        except Exception as e:
            self.record(name, "failed", repr(e))
            log.error("✖ %s failed: %s", name, e)
            raise
        secs = time.time() - t0
        self.record(name, "success", f"{secs:.1f}s; result={out!r}"[:4000])
        log.info("✔ %s (%.1fs)", name, secs)
        return out


def main():
    load_dotenv()
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-9s %(message)s", datefmt="%H:%M:%S")

    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()
    run_id = f"{run_date:%Y%m%d}_{datetime.now(timezone.utc):%H%M%S}"
    mock = args.mock
    http = extract.http_session()
    fx_start = run_date - timedelta(days=int(os.getenv("FX_LOOKBACK_DAYS", "35")))
    log.info("run_id=%s run_date=%s mock=%s", run_id, run_date, mock)

    # ---------------- 1. EXTRACT (sources that don't depend on Snowflake) ----------------
    files = {
        "web":       extract.write_landing("web", extract.web_orders(http, run_date, mock), run_id, run_date),
        "mobile":    extract.write_landing("mobile", extract.mobile_orders(http, run_date, mock), run_id, run_date),
        "crm":       extract.write_landing("crm", extract.crm_tier_events(http, run_date, mock), run_id, run_date),
        "fx":        extract.write_landing("fx", extract.fx_rates(http, fx_start, run_date, mock), run_id, run_date),
    }
    if args.dry_run:
        log.info("dry run: landing files written, Snowflake not touched: %s", files)
        return

    import snowflake_io as sf                     # imported here so --dry-run needs no connector
    conn = sf.connect(bootstrap=args.setup)
    run = Run(None, run_id)
    try:
        if args.setup:
            run.step("setup", sf.run_sql_file, conn, SQL / "00_setup.sql")
        run.conn = conn                           # ops.run_log exists from here on
        vars_ = {"run_id": run_id, "run_date": run_date.isoformat()}

        # ---------------- 2. LOAD raw files into bronze ----------------
        stage = lambda src: f"{src}/{run_date.isoformat()}/{run_id}"
        run.step("load web orders",    sf.load_file, conn, files["web"],    "bronze.orders_raw",    stage("orders_web"))
        run.step("load mobile orders", sf.load_file, conn, files["mobile"], "bronze.orders_raw",    stage("orders_mobile"))
        run.step("load crm",           sf.load_file, conn, files["crm"],    "bronze.customers_raw", stage("crm"))
        run.step("load fx",            sf.load_file, conn, files["fx"],     "bronze.fx_raw",        stage("fx"))

        # ---------------- 3. TRANSFORM inside Snowflake ----------------
        run.step("10 cleanse orders",  sf.run_sql_file, conn, SQL / "10_silver_orders_clean.sql", vars_)
        run.step("20 deduplicate",     sf.run_sql_file, conn, SQL / "20_silver_orders_dedup.sql", vars_)

        # Pincodes depend on the orders: only look up valid ones we have never seen.
        pins = [r[0] for r in sf.query_all(conn, """
            SELECT DISTINCT o.pincode FROM silver.orders_dedup o
            WHERE NOT EXISTS (SELECT 1 FROM ref.pincode_geo g WHERE g.pincode = o.pincode)""")]
        log.info("new pincodes to look up: %s", pins)
        pin_file = extract.write_landing("pincode", extract.pincodes(http, pins, mock), run_id, run_date)
        run.step("load pincodes",      sf.load_file, conn, pin_file, "bronze.pincode_raw", stage("pincode"))

        run.step("30 customers scd2",  sf.run_sql_file, conn, SQL / "30_dim_customers_scd2.sql", vars_)
        run.step("31 fx daily",        sf.run_sql_file, conn, SQL / "31_ref_fx_daily.sql", vars_)
        run.step("32 pincode geo",     sf.run_sql_file, conn, SQL / "32_ref_pincode_geo.sql", vars_)
        run.step("40 enrich + gold",   sf.run_sql_file, conn, SQL / "40_gold_fct_orders.sql", vars_)

        # ---------------- 4. CHECK ----------------
        run.step("quality checks", quality_checks, conn, args.strict)
        n, revenue, points = sf.query_one(conn,
            "SELECT COUNT(*), SUM(amount_inr), SUM(loyalty_points) FROM gold.fct_orders")
        log.info("GOLD: %s orders, revenue ₹%s, %s loyalty points", n, revenue, points)
    finally:
        conn.close()


def quality_checks(conn, strict):
    """Assertions after the run. 'fail' stops the pipeline; 'warn' only logs,
    unless --strict is given."""
    import snowflake_io as sf
    max_q = float(os.getenv("QUARANTINE_MAX_RATE", "0.05"))
    checks = [
        ("no fan-out in enrichment (rows out - rows in)",
         "SELECT (SELECT COUNT(*) FROM silver.orders_enriched) - (SELECT COUNT(*) FROM silver.orders_dedup)",
         lambda v: v == 0, "fail"),
        ("one gold row per order_id (duplicates)",
         "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM gold.fct_orders", lambda v: v == 0, "fail"),
        ("orders with no customer match",
         "SELECT COUNT_IF(cust_id IS NULL) FROM silver.orders_enriched", lambda v: v == 0, "warn"),
        ("orders with an amount but no FX rate",
         "SELECT COUNT_IF(amount IS NOT NULL AND fx_rate IS NULL) FROM silver.orders_enriched",
         lambda v: v == 0, "warn"),
        ("orders with no city",
         "SELECT COUNT_IF(city IS NULL) FROM silver.orders_enriched", lambda v: v == 0, "warn"),
        (f"quarantine rate (max {max_q:.0%})",
         "SELECT COALESCE(COUNT_IF(ARRAY_SIZE(reasons) > 0) / NULLIF(COUNT(*), 0), 0) FROM silver.orders_checked",
         lambda v: float(v) <= max_q, "warn"),
        ("orders in silver.orders_dedup with future order date",
         "SELECT COUNT_IF(order_date > CURRENT_DATE()) FROM silver.orders_dedup",
         lambda v: v == 0, "fail"),
    ]
    problems = []
    for name, sql, ok, severity in checks:
        value = sf.query_one(conn, sql)[0]
        good = ok(value)
        log.info("   %-48s %-8s %s", name, value, "OK" if good else severity.upper())
        if not good and (severity == "fail" or strict):
            problems.append(f"{name} = {value}")
    if problems:
        raise RuntimeError("quality checks failed: " + "; ".join(problems))
    return "passed"


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.getLogger("pipeline").error("pipeline failed: %s", exc)
        sys.exit(1)
