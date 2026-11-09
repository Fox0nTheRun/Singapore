USE hdb_insights_demo;

-- Keep this ID in the current session for subsequent CRUD steps.
SET @demo_id = CONCAT('demo:', UUID());

START TRANSACTION;

INSERT INTO demo_resale_transaction (
    demo_record_id,
    record_kind,
    seed_record_id,
    base_data_release_id,
    registration_month,
    town_id,
    flat_type_code,
    block,
    street_name,
    storey_lower,
    storey_upper,
    floor_area_sqm,
    flat_model,
    lease_commence_year,
    remaining_lease_months,
    resale_price
)
SELECT
    @demo_id,
    'demo',
    s.seed_record_id,
    s.base_data_release_id,
    r.registration_month,
    r.town_id,
    r.flat_type_code,
    r.block,
    r.street_name,
    r.storey_lower,
    r.storey_upper,
    r.floor_area_sqm,
    r.flat_model,
    r.lease_commence_year,
    r.remaining_lease_months,
    r.resale_price
FROM demo_seed AS s
JOIN hdb_insights.resale_transaction AS r
    ON r.record_id = s.seed_record_id
   AND r.dataset_id = s.dataset_id
   AND r.source_file_sha256 = s.source_file_sha256
   AND r.source_row_number = s.source_row_number
JOIN hdb_insights.application_metadata AS m
    ON m.metadata_id = 1
   AND m.data_release_id = s.base_data_release_id
ORDER BY s.seed_record_id
LIMIT 1;

SELECT ROW_COUNT() AS inserted_rows;

SELECT *
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

-- Commit manually after checking the result.