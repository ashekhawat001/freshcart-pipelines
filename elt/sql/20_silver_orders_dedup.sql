-- =====================================================================
-- SILVER 2: one row per order_id, newest version wins.
-- Ties on updated_at are broken by arrival order, so reruns give the same answer.
-- =====================================================================
CREATE OR REPLACE TABLE silver.orders_dedup AS
SELECT *
FROM silver.orders_clean
QUALIFY ROW_NUMBER() OVER (
          PARTITION BY order_id
          ORDER BY updated_at DESC, ingest_seq DESC
        ) = 1;
