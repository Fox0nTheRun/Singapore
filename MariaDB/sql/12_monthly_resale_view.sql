-- HDB Insights | HDBI-1.0.0
-- F01: monthly statistics by town and flat type
USE hdb_insights;

SET SESSION div_precision_increment = 12;

CREATE VIEW v_monthly_resale_summary AS
SELECT
    r.registration_month,
    t.town_name,
    r.flat_type_code,
    COUNT(*) AS transaction_count,
    SUM(r.resale_price) AS total_resale_price,
    AVG(r.resale_price) AS average_price,
    AVG(r.resale_price / r.floor_area_sqm)
        AS average_price_per_sqm
FROM resale_transaction AS r
JOIN town AS t ON t.town_id = r.town_id
GROUP BY
    r.registration_month,
    t.town_name,
    r.flat_type_code;

-- Verify against the earlier monthly query.
SELECT
    registration_month,
    transaction_count,
    ROUND(average_price, 2) AS average_price,
    ROUND(average_price_per_sqm, 2) AS average_price_per_sqm
FROM v_monthly_resale_summary
WHERE town_name = 'ANG MO KIO'
  AND flat_type_code = '4_ROOM'
  AND registration_month BETWEEN '2020-01' AND '2020-12'
ORDER BY registration_month;