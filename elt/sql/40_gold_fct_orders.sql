-- =====================================================================
-- ENRICH + PUBLISH
-- 1. silver.orders_enriched: point-in-time joins to customer tier and FX rate,
--    computed columns, geography. LEFT JOINs so no order is silently lost.
-- 2. gold.fct_orders: idempotent MERGE. Re-running changes nothing unless a
--    value actually changed (row_hash).
-- =====================================================================
CREATE OR REPLACE TABLE silver.orders_enriched AS
SELECT o.*,
       c.cust_id, c.tier,
       m.multiplier,
       fx.rate_to_inr                              AS fx_rate,
       ROUND(o.amount * fx.rate_to_inr, 2)         AS amount_inr,
       FLOOR(amount_inr / 100) * m.multiplier      AS loyalty_points,
       amount_inr >= 2000                          AS is_high_value,
       g.city, g.state, g.region
FROM silver.orders_dedup o
LEFT JOIN dim.customers_scd2 c
       ON  c.email = o.email
       AND o.order_date BETWEEN c.valid_from AND c.valid_to     -- tier ON the order date
LEFT JOIN ref.tier_multiplier m ON m.tier = c.tier
LEFT JOIN ref.fx_daily fx
       ON  fx.currency = o.currency AND fx.rate_date = o.order_date  -- rate OF the order date
LEFT JOIN ref.pincode_geo g ON g.pincode = o.pincode;

MERGE INTO gold.fct_orders t
USING (
  SELECT order_id, order_date, cust_id, email, tier, multiplier, amount, currency, fx_rate,
         amount_inr, loyalty_points, is_high_value, city, state, region, updated_at,
         HASH(order_date, cust_id, email, tier, multiplier, amount, currency, fx_rate,
              amount_inr, loyalty_points, is_high_value, city, state, region, updated_at) AS row_hash
  FROM silver.orders_enriched
) s
ON t.order_id = s.order_id
WHEN MATCHED AND t.row_hash <> s.row_hash THEN UPDATE SET
  order_date = s.order_date, cust_id = s.cust_id, email = s.email, tier = s.tier,
  multiplier = s.multiplier, amount = s.amount, currency = s.currency, fx_rate = s.fx_rate,
  amount_inr = s.amount_inr, loyalty_points = s.loyalty_points, is_high_value = s.is_high_value,
  city = s.city, state = s.state, region = s.region, updated_at = s.updated_at,
  row_hash = s.row_hash, published_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT
  (order_id, order_date, cust_id, email, tier, multiplier, amount, currency, fx_rate, amount_inr,
   loyalty_points, is_high_value, city, state, region, updated_at, row_hash, published_at)
VALUES
  (s.order_id, s.order_date, s.cust_id, s.email, s.tier, s.multiplier, s.amount, s.currency,
   s.fx_rate, s.amount_inr, s.loyalty_points, s.is_high_value, s.city, s.state, s.region,
   s.updated_at, s.row_hash, CURRENT_TIMESTAMP());
