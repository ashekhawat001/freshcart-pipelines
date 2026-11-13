-- =====================================================================
-- REF: add newly looked-up pincodes to ref.pincode_geo.
-- India Post gives district and state; the company's sales region comes from
-- the ref.state_region seed table.
-- =====================================================================
MERGE INTO ref.pincode_geo t
USING (
  SELECT p.pincode, p.city, p.state, sr.region
  FROM (
    SELECT raw:pincode::STRING                                  AS pincode,
           raw:response[0]:PostOffice[0]:District::STRING       AS city,
           raw:response[0]:PostOffice[0]:State::STRING          AS state,
           loaded_at, ingest_seq
    FROM bronze.pincode_raw
    WHERE raw:response[0]:Status::STRING = 'Success'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY pincode ORDER BY loaded_at DESC, ingest_seq DESC) = 1
  ) p
  LEFT JOIN ref.state_region sr ON sr.state = p.state
) s
ON t.pincode = s.pincode
WHEN MATCHED AND (t.city <> s.city OR t.state <> s.state OR NVL(t.region,'') <> NVL(s.region,''))
  THEN UPDATE SET city = s.city, state = s.state, region = s.region, updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED
  THEN INSERT (pincode, city, state, region, updated_at)
       VALUES (s.pincode, s.city, s.state, s.region, CURRENT_TIMESTAMP());
