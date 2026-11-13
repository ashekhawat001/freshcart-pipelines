-- =====================================================================
-- SILVER 1: unify the two order APIs, cleanse, validate, quarantine.
-- Input : bronze.orders_raw (raw JSON from 'web' and 'mobile')
-- Output: silver.orders_checked (all rows + reasons), silver.orders_clean (good rows),
--         quarantine.orders (bad rows, appended once per row)
-- =====================================================================
CREATE OR REPLACE TRANSIENT TABLE silver.orders_checked AS
WITH unified AS (
  -- The two APIs name and nest fields differently; map both to one set of columns.
  SELECT ingest_seq, source,
         raw:order_id::STRING   AS order_id,
         raw:cust_email::STRING AS cust_email,
         raw:cust_name::STRING  AS cust_name,
         raw:order_date::STRING AS order_date,
         raw:amount::STRING     AS amount,
         raw:currency::STRING   AS currency,
         raw:pincode::STRING    AS pincode,
         raw:updated_at::STRING AS updated_at
  FROM bronze.orders_raw WHERE source = 'web'
  UNION ALL
  SELECT ingest_seq, source,
         raw:orderId::STRING, raw:customer.email::STRING, raw:customer.name::STRING,
         raw:orderDate::STRING, raw:total.value::STRING, raw:total.currency::STRING,
         raw:deliveryPin::STRING, raw:updatedAt::STRING
  FROM bronze.orders_raw WHERE source = 'mobile'
),
typed AS (
  SELECT
    ingest_seq, source,
    TRIM(order_id)                                    AS order_id,
    LOWER(TRIM(cust_email))                           AS email,
    INITCAP(RTRIM(TRIM(cust_name), '.'))              AS name,
    COALESCE(
      TRY_TO_DATE(order_date, 'YYYY-MM-DD'),
      TRY_TO_DATE(order_date, 'DD/MM/YYYY'),          -- mobile API sends day first
      TRY_TO_DATE(order_date, 'MON DD, YYYY')
    )                                                 AS order_date,
    TRY_TO_DECIMAL(REGEXP_REPLACE(amount, '[^0-9.-]', ''), 12, 2) AS amount,
    UPPER(TRIM(currency))                             AS currency,
    TRIM(pincode)                                     AS pincode,
    TRY_TO_TIMESTAMP_NTZ(updated_at)                  AS updated_at
  FROM unified
)
SELECT *,
ARRAY_CONSTRUCT_COMPACT(
    IFF(order_id IS NULL, 'missing_order_id', NULL),
    IFF(email IS NULL OR NOT REGEXP_LIKE(email, '^[^@\\s]+@[^@\\s]+\\.[a-z]{2,}$'), 'bad_email', NULL),
    IFF(pincode IS NULL OR NOT REGEXP_LIKE(pincode, '^[1-9][0-9]{5}$'), 'bad_pincode', NULL),
    IFF(order_date IS NULL, 'unparseable_date', NULL),
    IFF(updated_at IS NULL, 'unparseable_updated_at', NULL),
    IFF(amount <= 0, 'non_positive_amount', NULL),
    IFF(currency IS NULL OR currency NOT IN ('INR', 'USD'), 'unsupported_currency', NULL)
  ) AS reasons
FROM typed;

-- Good rows
CREATE OR REPLACE TABLE silver.orders_clean AS
SELECT * EXCLUDE reasons, (amount IS NULL) AS amount_missing
FROM silver.orders_checked
WHERE ARRAY_SIZE(reasons) = 0;

-- Bad rows: kept with their reasons. The NOT EXISTS stops the same bad record being
-- quarantined again when a later run re-extracts it (same source, order, version).
INSERT INTO quarantine.orders (run_id, ingest_seq, source, order_id, reasons, row_data)
SELECT $run_id, c.ingest_seq, c.source, c.order_id, c.reasons, OBJECT_CONSTRUCT(*)
FROM silver.orders_checked c
WHERE ARRAY_SIZE(c.reasons) > 0
  AND NOT EXISTS (
        SELECT 1 FROM quarantine.orders q
        WHERE q.source = c.source
          AND EQUAL_NULL(q.order_id, c.order_id)
          AND EQUAL_NULL(q.row_data:updated_at::TIMESTAMP_NTZ, c.updated_at))
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.source, c.order_id, c.updated_at
                           ORDER BY c.ingest_seq DESC) = 1;
