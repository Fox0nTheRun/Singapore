USE hdb_insights;

SELECT
    UTC_TIMESTAMP() AS checked_at_utc,
    VERSION() AS database_version;

SELECT *
FROM application_metadata;

-- Check all eight fact-table row counts.
SELECT
    checks.*,
    CASE
        WHEN actual_rows = expected_rows THEN 'PASS'
        ELSE 'FAIL'
    END AS result
FROM (
    SELECT 'resale_transaction' AS table_name,
           240468 AS expected_rows, COUNT(*) AS actual_rows
    FROM resale_transaction

    UNION ALL
    SELECT 'age_by_flat_type', 63, COUNT(*)
    FROM age_by_flat_type

    UNION ALL
    SELECT 'age_stats_by_flat_type', 21, COUNT(*)
    FROM age_stats_by_flat_type

    UNION ALL
    SELECT 'population_15_plus_by_flat_type', 18, COUNT(*)
    FROM population_15_plus_by_flat_type

    UNION ALL
    SELECT 'age_by_ethnicity', 45, COUNT(*)
    FROM age_by_ethnicity

    UNION ALL
    SELECT 'age_stats_by_ethnicity', 15, COUNT(*)
    FROM age_stats_by_ethnicity

    UNION ALL
    SELECT 'population_15_plus_by_ethnicity', 12, COUNT(*)
    FROM population_15_plus_by_ethnicity

    UNION ALL
    SELECT 'mobility_observation', 1440, COUNT(*)
    FROM mobility_observation
) AS checks
ORDER BY table_name;

-- Preserve unresolved values rather than replacing them with zero.
SELECT
    COUNT(*) AS unresolved_rows,
    COUNT(`count`) AS unresolved_non_null_counts,
    CASE
        WHEN COUNT(*) = 73 AND COUNT(`count`) = 0
        THEN 'PASS'
        ELSE 'FAIL'
    END AS result
FROM mobility_observation
WHERE count_status = 'unresolved_dash';

-- Every reported count must be present and non-negative.
SELECT
    COUNT(*) AS invalid_reported_rows,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS result
FROM mobility_observation
WHERE count_status = 'reported'
  AND (`count` IS NULL OR `count` < 0);

-- Every resale row must resolve to its reference records.
SELECT
    COUNT(*) AS orphan_resale_rows,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS result
FROM resale_transaction AS r
LEFT JOIN town AS t
    ON t.town_id = r.town_id
LEFT JOIN flat_type AS f
    ON f.flat_type_code = r.flat_type_code
LEFT JOIN source_dataset AS s
    ON s.dataset_id = r.dataset_id
   AND s.source_file_sha256 = r.source_file_sha256
WHERE t.town_id IS NULL
   OR f.flat_type_code IS NULL
   OR s.dataset_id IS NULL;