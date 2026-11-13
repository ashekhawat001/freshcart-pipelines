-- =====================================================================
-- REF: daily FX rates to INR, with no gaps.
-- 1. Flatten the API's {"rates": {"2026-09-01": {"INR": 83.2}, ...}} into rows.
-- 2. Rates are not published on weekends/holidays: fill each missing day with the
--    previous published rate, so every order date finds a rate.
-- 3. Add INR = 1.0 for every day, so rupee orders join like any other.
-- =====================================================================
CREATE OR REPLACE TABLE ref.fx_daily AS
WITH published AS (
  SELECT r.raw:base::STRING          AS currency,
         f.key::DATE                 AS rate_date,
         f.value:INR::NUMBER(12,4)   AS rate_to_inr
  FROM bronze.fx_raw r, LATERAL FLATTEN(input => r.raw:rates) f
  QUALIFY ROW_NUMBER() OVER (PARTITION BY currency, rate_date
                             ORDER BY r.loaded_at DESC, r.ingest_seq DESC) = 1
),
bounds AS (
  SELECT MIN(rate_date) AS d0, GREATEST(MAX(rate_date), CURRENT_DATE()) AS d1 FROM published
),
spine AS (                                   -- one row per calendar day d0..d1
  SELECT DATEADD(day, ROW_NUMBER() OVER (ORDER BY SEQ4()) - 1, b.d0) AS d
  FROM bounds b, TABLE(GENERATOR(ROWCOUNT => 4000))
  QUALIFY d <= (SELECT d1 FROM bounds)
),
filled AS (
  SELECT c.currency, s.d AS rate_date,
         LAST_VALUE(p.rate_to_inr) IGNORE NULLS OVER (
           PARTITION BY c.currency ORDER BY s.d
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS rate_to_inr,
         p.rate_to_inr IS NULL AS is_carried_forward
  FROM spine s
  CROSS JOIN (SELECT DISTINCT currency FROM published) c
  LEFT JOIN published p ON p.currency = c.currency AND p.rate_date = s.d
)
SELECT currency, rate_date, rate_to_inr, is_carried_forward FROM filled
UNION ALL
SELECT 'INR', d, 1.0, FALSE FROM spine;
