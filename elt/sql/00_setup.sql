-- =====================================================================
-- One-time setup. Run with:  python run_pipeline.py --setup --mock
-- Needs a role that can create warehouses and databases (e.g. SYSADMIN).
-- Safe to re-run: everything is IF NOT EXISTS, except the two seed tables.
-- =====================================================================
CREATE WAREHOUSE IF NOT EXISTS FRESHCART_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
USE WAREHOUSE FRESHCART_WH;

CREATE DATABASE IF NOT EXISTS FRESHCART;
USE DATABASE FRESHCART;

CREATE SCHEMA IF NOT EXISTS bronze;      -- raw API responses, unchanged
CREATE SCHEMA IF NOT EXISTS silver;      -- cleaned, typed, deduplicated
CREATE SCHEMA IF NOT EXISTS dim;         -- dimensions (customers)
CREATE SCHEMA IF NOT EXISTS ref;         -- reference data (fx, pincodes, tiers)
CREATE SCHEMA IF NOT EXISTS gold;        -- business-ready tables
CREATE SCHEMA IF NOT EXISTS quarantine;  -- rows that failed validation
CREATE SCHEMA IF NOT EXISTS ops;         -- pipeline run log

-- Landing area inside Snowflake for the files Python uploads
CREATE FILE FORMAT IF NOT EXISTS bronze.ff_ndjson TYPE = JSON COMPRESSION = AUTO;
CREATE STAGE IF NOT EXISTS bronze.landing FILE_FORMAT = bronze.ff_ndjson;

-- ---------- BRONZE: one table per source, raw JSON in a VARIANT column ----------
CREATE TABLE IF NOT EXISTS bronze.orders_raw (
  ingest_seq   NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER,   -- arrival order
  source       STRING,          -- 'web' or 'mobile'
  raw          VARIANT,         -- the API record exactly as received
  run_id       STRING,
  extracted_at TIMESTAMP_TZ,
  src_file     STRING,
  src_row      NUMBER,
  loaded_at    TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
CREATE TABLE IF NOT EXISTS bronze.customers_raw (
  ingest_seq NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER, source STRING, raw VARIANT,
  run_id STRING, extracted_at TIMESTAMP_TZ, src_file STRING, src_row NUMBER,
  loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
CREATE TABLE IF NOT EXISTS bronze.fx_raw (
  ingest_seq NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER, source STRING, raw VARIANT,
  run_id STRING, extracted_at TIMESTAMP_TZ, src_file STRING, src_row NUMBER,
  loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
CREATE TABLE IF NOT EXISTS bronze.pincode_raw (
  ingest_seq NUMBER AUTOINCREMENT START 1 INCREMENT 1 ORDER, source STRING, raw VARIANT,
  run_id STRING, extracted_at TIMESTAMP_TZ, src_file STRING, src_row NUMBER,
  loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

-- ---------- REF: small hand-maintained seed tables ----------
CREATE OR REPLACE TABLE ref.tier_multiplier AS
SELECT * FROM VALUES ('Silver', 1), ('Gold', 2), ('Platinum', 3) AS v(tier, multiplier);

CREATE OR REPLACE TABLE ref.state_region AS
SELECT * FROM VALUES
  ('Tamil Nadu','South'), ('Karnataka','South'), ('Kerala','South'), ('Andhra Pradesh','South'),
  ('Telangana','South'), ('Puducherry','South'),
  ('Maharashtra','West'), ('Gujarat','West'), ('Goa','West'), ('Rajasthan','West'),
  ('Delhi','North'), ('Haryana','North'), ('Punjab','North'), ('Uttar Pradesh','North'),
  ('Himachal Pradesh','North'), ('Jammu and Kashmir','North'), ('Uttarakhand','North'),
  ('West Bengal','East'), ('Odisha','East'), ('Bihar','East'), ('Jharkhand','East'), ('Assam','East'),
  ('Madhya Pradesh','Central'), ('Chhattisgarh','Central')
  AS v(state, region);

-- Filled incrementally from the India Post API (see 32_ref_pincode_geo.sql)
CREATE TABLE IF NOT EXISTS ref.pincode_geo (
  pincode STRING PRIMARY KEY, city STRING, state STRING, region STRING,
  updated_at TIMESTAMP_LTZ
);

-- ---------- QUARANTINE, GOLD, OPS ----------
CREATE TABLE IF NOT EXISTS quarantine.orders (
  run_id STRING, quarantined_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
  ingest_seq NUMBER, source STRING, order_id STRING, reasons ARRAY, row_data VARIANT
);

CREATE TABLE IF NOT EXISTS gold.fct_orders (
  order_id STRING PRIMARY KEY, order_date DATE, cust_id STRING, email STRING,
  tier STRING, multiplier NUMBER, amount NUMBER(12,2), currency STRING,
  fx_rate NUMBER(12,4), amount_inr NUMBER(14,2), loyalty_points NUMBER,
  is_high_value BOOLEAN, city STRING, state STRING, region STRING,
  updated_at TIMESTAMP_NTZ, row_hash NUMBER, published_at TIMESTAMP_LTZ
);

CREATE TABLE IF NOT EXISTS ops.run_log (
  run_id STRING, step STRING, status STRING, detail STRING,
  logged_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);
