-- HDB Insights | HDBI-1.0.0
-- F02 Demographic Explorer: flat-type profile
USE hdb_insights;

SET @profile_flat_type = '4_ROOM';
SET @survey_year = 2018;

-- One summary row for the selected profile.
SELECT
    s.survey_year,
    s.flat_type_code,
    f.display_label,
    s.average_age,
    s.median_age,
    p.population_15_plus,
    CASE
        WHEN p.population_15_plus IS NULL THEN 'not_provided'
        ELSE 'reported'
    END AS population_status
FROM age_stats_by_flat_type AS s
JOIN flat_type AS f
    ON f.flat_type_code = s.flat_type_code
LEFT JOIN population_15_plus_by_flat_type AS p
    ON p.survey_year = s.survey_year
   AND p.flat_type_code = s.flat_type_code
WHERE s.flat_type_code = @profile_flat_type
  AND s.survey_year = @survey_year;

-- Age distribution is returned separately to avoid
-- repeating the population value across three rows.
SELECT
    a.survey_year,
    a.flat_type_code,
    a.age_group_code,
    g.display_label AS age_group_label,
    a.percentage
FROM age_by_flat_type AS a
JOIN age_group AS g
    ON g.age_group_code = a.age_group_code
WHERE a.flat_type_code = @profile_flat_type
  AND a.survey_year = @survey_year
ORDER BY g.sort_order;