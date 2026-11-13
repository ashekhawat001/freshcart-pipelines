"""LOAD: connect to Snowflake, upload landing files to an internal stage (PUT) and copy
them into the bronze tables (COPY INTO). Also runs the SQL transformation files."""
import logging
import os
from pathlib import Path

import snowflake.connector

log = logging.getLogger("snowflake")


def connect(bootstrap=False):
    """bootstrap=True connects without a database/warehouse (they may not exist yet
    before --setup has run; 00_setup.sql creates them and USEs them)."""
    kw = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.getenv("SNOWFLAKE_ROLE"),
        "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE"),
        "database": os.getenv("SNOWFLAKE_DATABASE"),
        "session_parameters": {"QUERY_TAG": "freshcart_elt"},
    }
    if bootstrap:
        kw.pop("warehouse"); kw.pop("database")
    if os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE"):          # key-pair auth (recommended)
        kw["private_key_file"] = os.environ["SNOWFLAKE_PRIVATE_KEY_FILE"]
        kw["private_key_file_pwd"] = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE_PWD")
    elif os.getenv("SNOWFLAKE_AUTHENTICATOR"):           # e.g. externalbrowser (SSO)
        kw["authenticator"] = os.environ["SNOWFLAKE_AUTHENTICATOR"]
    else:
        kw["password"] = os.environ["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(**{k: v for k, v in kw.items() if v})


def run_sql_file(conn, path, variables=None):
    """Run every statement in a .sql file. Variables become session variables, so the SQL
    can use them as $run_id, $run_date."""
    text = Path(path).read_text(encoding="utf-8")
    prefix = "".join(f"SET {k} = '{v}';\n" for k, v in (variables or {}).items())
    for cur in conn.execute_string(prefix + text, remove_comments=True):
        cur.close()
    log.info("ran %s", Path(path).name)


def query_one(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def query_all(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def load_file(conn, local_path, table, stage_dir):
    """PUT one landing file to @bronze.landing/<stage_dir>/ then COPY it into <table>.

    COPY remembers which files it has loaded (for 64 days), so re-running this for the
    same file loads nothing the second time: the load step is idempotent."""
    if local_path is None:
        return 0
    uri = "file://" + Path(local_path).resolve().as_posix()
    with conn.cursor() as cur:
        cur.execute(f"PUT '{uri}' @bronze.landing/{stage_dir}/ AUTO_COMPRESS=FALSE OVERWRITE=FALSE")
        cur.execute(f"""
            COPY INTO {table} (source, raw, run_id, extracted_at, src_file, src_row)
            FROM (
              SELECT $1:source::STRING, $1:data, $1:run_id::STRING,
                     $1:extracted_at::TIMESTAMP_TZ, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER
              FROM @bronze.landing/{stage_dir}/
            )
            FILE_FORMAT = (FORMAT_NAME = 'bronze.ff_ndjson')
            ON_ERROR = 'ABORT_STATEMENT'
        """)
        rows = cur.fetchall()
    # COPY returns one row per file: (file, status, rows_parsed, rows_loaded, ...),
    # or a single message row when there was nothing new to load.
    loaded = sum(int(r[3]) for r in rows if len(r) > 3 and str(r[1]).startswith(("LOADED", "PARTIALLY")))
    log.info("%s: %d rows copied into %s", Path(local_path).name, loaded, table)
    return loaded
