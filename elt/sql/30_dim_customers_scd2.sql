-- =====================================================================
-- DIM: build the SCD Type 2 customer table from the CRM's tier-change log.
-- Each change starts a period; the period ends the day before the next change.
-- =====================================================================
CREATE OR REPLACE TABLE dim.customers_scd2 AS
WITH events AS (
  SELECT raw:cust_id::STRING                 AS cust_id,
         LOWER(TRIM(raw:email::STRING))      AS email,
         INITCAP(TRIM(raw:tier::STRING))     AS tier,
         TRY_TO_DATE(raw:effective_from::STRING) AS valid_from,
         loaded_at, ingest_seq
  FROM bronze.customers_raw
  -- the same event may be extracted on many runs; keep the latest copy
  QUALIFY ROW_NUMBER() OVER (PARTITION BY cust_id, valid_from
                             ORDER BY loaded_at DESC, ingest_seq DESC) = 1
)
SELECT cust_id, email, tier, valid_from,
       COALESCE(DATEADD(day, -1, LEAD(valid_from) OVER (PARTITION BY cust_id ORDER BY valid_from)),
                '9999-12-31'::DATE)                                       AS valid_to,
       LEAD(valid_from) OVER (PARTITION BY cust_id ORDER BY valid_from) IS NULL AS is_current
FROM events
WHERE cust_id IS NOT NULL AND valid_from IS NOT NULL;
