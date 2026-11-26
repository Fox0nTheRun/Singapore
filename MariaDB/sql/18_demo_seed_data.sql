USE hdb_insights_demo;

START TRANSACTION;

-- Copy the town reference data.
INSERT INTO town (town_id, town_name)
SELECT town_id, town_name
FROM hdb_insights.town;

-- ALL is an aggregate category, not a valid transaction flat type.
INSERT INTO flat_type (flat_type_code, display_label)
SELECT flat_type_code, display_label
FROM hdb_insights.flat_type
WHERE flat_type_code <> 'ALL';

-- Copy authentic source lineage for 10 deterministically selected records.
INSERT INTO demo_seed (
    seed_record_id,
    base_data_release_id,
    dataset_id,
    source_file_sha256,
    source_row_number
)
SELECT
    r.record_id,
    m.data_release_id,
    r.dataset_id,
    r.source_file_sha256,
    r.source_row_number
FROM hdb_insights.resale_transaction AS r
CROSS JOIN hdb_insights.application_metadata AS m
WHERE m.metadata_id = 1
  AND m.contract_version = 'HDBI-1.0.0'
  AND m.data_release_id = '150921447b27_c1.0.0_t0.1.2'
ORDER BY r.record_id
LIMIT 10;

-- Inspect counts before committing.
SELECT 'town' AS table_name, COUNT(*) AS actual_rows, 26 AS expected_rows
FROM town
UNION ALL
SELECT 'flat_type', COUNT(*), 7
FROM flat_type
UNION ALL
SELECT 'demo_seed', COUNT(*), 10
FROM demo_seed
UNION ALL
SELECT 'demo_resale_transaction', COUNT(*), 0
FROM demo_resale_transaction;

-- Verify every seed matches the analytical source and active release.
SELECT COUNT(*) AS matching_seed_rows
FROM demo_seed AS s
JOIN hdb_insights.resale_transaction AS r
    ON r.record_id = s.seed_record_id
   AND r.dataset_id = s.dataset_id
   AND r.source_file_sha256 = s.source_file_sha256
   AND r.source_row_number = s.source_row_number
JOIN hdb_insights.application_metadata AS m
    ON m.metadata_id = 1
   AND m.data_release_id = s.base_data_release_id;

-- COMMIT deliberately left for manual execution after checking results.