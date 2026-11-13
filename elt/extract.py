"""EXTRACT: call each API and save the responses unchanged as gzipped newline-delimited
JSON files in the local landing folder.

No cleaning happens here (that is the point of ELT). Each record is wrapped in a
small envelope so we always know where and when it came from:

    {"source": "web", "run_id": "...", "extracted_at": "...", "data": {<original record>}}
"""
import gzip
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import mock_data

log = logging.getLogger("extract")


# ---------------------------------------------------------------- HTTP helpers
def http_session():
    """A requests session that retries transient failures with exponential backoff
    (1 s, 2 s, 4 s, ...) and honours the server's Retry-After header on 429."""
    retry = Retry(total=5, backoff_factor=1.0,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",), respect_retry_after_header=True)
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = "freshcart-elt/1.0"
    return s


def _auth(token_env):
    token = os.getenv(token_env)
    return {"Authorization": f"Bearer {token}"} if token else {}


def paginate(session, url, params=None, headers=None, items_key="data", next_key="next",
             timeout=30, max_pages=10_000):
    """Yield records from an API that returns {"data": [...], "next": "<url or null>"}.
    Change items_key / next_key to match your API (e.g. "results" / "next_page_url").
    If your API uses page numbers instead, loop on params["page"] until a page is empty."""
    page_url, page_params = url, dict(params or {})
    for _ in range(max_pages):
        r = session.get(page_url, params=page_params, headers=headers, timeout=timeout)
        r.raise_for_status()
        body = r.json()
        items = body.get(items_key, []) if isinstance(body, dict) else body
        yield from items
        nxt = body.get(next_key) if isinstance(body, dict) else None
        if not nxt:
            return
        page_url, page_params = nxt, None      # the next link already carries the query
    raise RuntimeError(f"{url}: more than {max_pages} pages, stopping")


# ---------------------------------------------------------------- landing files
def write_landing(source, records, run_id, run_date):
    """Write records as one .json.gz file per source per run. Returns the path, or None."""
    records = list(records)
    if not records:
        log.info("%s: 0 records, nothing written", source)
        return None
    folder = Path(os.getenv("LANDING_DIR", "landing")) / source / run_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{source}__{run_id}.json.gz"
    now = datetime.now(timezone.utc).isoformat()
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps({"source": source, "run_id": run_id, "extracted_at": now,
                                "data": rec}, ensure_ascii=False) + "\n")
    log.info("%s: %d records -> %s", source, len(records), path)
    return path


# ---------------------------------------------------------------- one function per API
def web_orders(session, run_date, mock=False):
    if mock:
        return mock_data.WEB_ORDERS
    # Incremental pull: everything changed since the day before the logical run date.
    since = (run_date - timedelta(days=1)).isoformat()
    return paginate(session, os.environ["WEB_ORDERS_URL"], params={"updated_since": since},
                    headers=_auth("WEB_ORDERS_TOKEN"))


def mobile_orders(session, run_date, mock=False):
    if mock:
        return mock_data.MOBILE_ORDERS
    since = (run_date - timedelta(days=1)).isoformat()
    return paginate(session, os.environ["MOBILE_ORDERS_URL"], params={"updatedSince": since},
                    headers=_auth("MOBILE_ORDERS_TOKEN"), items_key="orders", next_key="nextPage")


def crm_tier_events(session, run_date, mock=False):
    if mock:
        return mock_data.CRM_TIER_EVENTS
    return paginate(session, os.environ["CRM_TIER_EVENTS_URL"], headers=_auth("CRM_TOKEN"))


def fx_rates(session, start, end, mock=False):
    """Daily USD->INR (and any other FX_BASES) rates from the Frankfurter API (ECB data).
    One record per base currency, kept exactly as the API returns it."""
    if mock:
        return mock_data.FX_RESPONSES
    base_url = os.getenv("FX_URL", "https://api.frankfurter.app")
    out = []
    for base in [b.strip() for b in os.getenv("FX_BASES", "USD").split(",") if b.strip()]:
        r = session.get(f"{base_url}/{start.isoformat()}..{end.isoformat()}",
                        params={"from": base, "to": "INR"}, timeout=30)
        r.raise_for_status()
        out.append(r.json())
    return out


def pincodes(session, pins, mock=False):
    """India Post lookup, one call per pincode. Only pincodes we don't know yet are asked."""
    base_url = os.getenv("PINCODE_URL", "https://api.postalpincode.in/pincode")
    out = []
    for pin in pins:
        if mock:
            resp = mock_data.pincode_response(pin)
        else:
            r = session.get(f"{base_url}/{pin}", timeout=30)
            r.raise_for_status()
            resp = r.json()
            time.sleep(0.2)                    # be polite to a free public API
        out.append({"pincode": pin, "response": resp})
    return out
