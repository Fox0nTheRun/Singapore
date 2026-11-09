-- HDB Insights | HDBI-1.0.0
-- F03 Mobility Explorer: transport-mode breakdown
USE hdb_insights;

SET SESSION div_precision_increment = 12;

-- "Total" selects the source's published all-workplace category.
SET @workplace_area = 'Total';
SET @residence_region = 'ALL';
SET @survey_year = 2020;

SELECT
    m.survey_year,
    m.workplace_area,
    m.residence_region_code,
    m.transport_mode_code,
    m.count,
    m.count_status,
    totals.count AS published_total,
    ROUND(
        m.count * 100.00 / NULLIF(totals.count, 0),
        2
    ) AS share_pct
FROM mobility_observation AS m
LEFT JOIN mobility_observation AS totals
    ON totals.survey_year = m.survey_year
   AND totals.workplace_area = m.workplace_area
   AND totals.residence_region_code = m.residence_region_code
   AND totals.transport_mode_code = 'ALL'
WHERE m.workplace_area = @workplace_area
  AND m.residence_region_code = @residence_region
  AND m.survey_year = @survey_year
  AND m.transport_mode_code <> 'ALL'
ORDER BY CASE m.transport_mode_code
    WHEN 'RAIL_BUS' THEN 1
    WHEN 'CAR_TAXI_PRIVATE_HIRE' THEN 2
    WHEN 'OTHER' THEN 3
    WHEN 'NO_TRANSPORT' THEN 4
END;