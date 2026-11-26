-- HDB Insights | HDBI-1.0.0
-- F01 Resale Explorer: summary and monthly trend
USE hdb_insights;

SET SESSION div_precision_increment = 12;

SET @filter_town = 'ANG MO KIO';
SET @filter_flat_type = '4_ROOM';
SET @start_month = '2020-01';
SET @end_month = '2020-12';

-- Summary across all matching transactions.
SELECT
    COUNT(*) AS transaction_count,
    ROUND(AVG(r.resale_price), 2) AS average_price,
    ROUND(AVG(r.resale_price / r.floor_area_sqm), 2)
        AS average_price_per_sqm
FROM resale_transaction AS r
JOIN town AS t ON t.town_id = r.town_id
WHERE t.town_name = @filter_town
  AND r.flat_type_code = @filter_flat_type
  AND r.registration_month BETWEEN @start_month AND @end_month;

-- Monthly trend across the same matching transactions.
SELECT
    r.registration_month,
    COUNT(*) AS transaction_count,
    ROUND(AVG(r.resale_price), 2) AS average_price,
    ROUND(AVG(r.resale_price / r.floor_area_sqm), 2)
        AS average_price_per_sqm
FROM resale_transaction AS r
JOIN town AS t ON t.town_id = r.town_id
WHERE t.town_name = @filter_town
  AND r.flat_type_code = @filter_flat_type
  AND r.registration_month BETWEEN @start_month AND @end_month
GROUP BY r.registration_month
ORDER BY r.registration_month;