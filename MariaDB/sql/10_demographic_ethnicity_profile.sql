-- HDB Insights | HDBI-1.0.0
-- F02 Demographic Explorer: ethnicity profile
USE hdb_insights;

SET @profile_ethnicity = 'CHINESE';
SET @survey_year = 2018;

-- Summary for the selected ethnicity and survey year.
SELECT
    s.survey_year,
    s.ethnic_group_code,
    e.display_label,
    s.average_age,
    s.median_age,
    p.population_15_plus,
    CASE
        WHEN p.population_15_plus IS NULL THEN 'not_provided'
        ELSE 'reported'
    END AS population_status
FROM age_stats_by_ethnicity AS s
JOIN ethnic_group AS e
    ON e.ethnic_group_code = s.ethnic_group_code
LEFT JOIN population_15_plus_by_ethnicity AS p
    ON p.survey_year = s.survey_year
   AND p.ethnic_group_code = s.ethnic_group_code
WHERE s.ethnic_group_code = @profile_ethnicity
  AND s.survey_year = @survey_year;

-- Age distribution in the agreed display order.
SELECT
    a.survey_year,
    a.ethnic_group_code,
    a.age_group_code,
    g.display_label AS age_group_label,
    a.percentage
FROM age_by_ethnicity AS a
JOIN age_group AS g
    ON g.age_group_code = a.age_group_code
WHERE a.ethnic_group_code = @profile_ethnicity
  AND a.survey_year = @survey_year
ORDER BY g.sort_order;