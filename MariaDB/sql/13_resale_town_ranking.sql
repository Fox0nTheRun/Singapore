-- HDB Insights | HDBI-1.0.0
-- F01: compare towns for one flat type and period
USE hdb_insights;

SET SESSION div_precision_increment = 12;

SET @ranking_flat_type = '4_ROOM';
SET @start_month = '2020-01';
SET @end_month = '2020-12';

WITH town_summary AS (
    SELECT
        t.town_name,
        COUNT(*) AS transaction_count,
        AVG(r.resale_price) AS average_price,
        AVG(r.resale_price / r.floor_area_sqm)
            AS average_price_per_sqm
    FROM resale_transaction AS r
    JOIN town AS t ON t.town_id = r.town_id
    WHERE r.flat_type_code = @ranking_flat_type
      AND r.registration_month BETWEEN @start_month AND @end_month
    GROUP BY t.town_name
),
ranked_towns AS (
    SELECT
        town_name,
        transaction_count,
        average_price,
        average_price_per_sqm,
        DENSE_RANK() OVER (
            ORDER BY average_price_per_sqm DESC
        ) AS price_rank
    FROM town_summary
)
SELECT
    price_rank,
    town_name,
    transaction_count,
    ROUND(average_price, 2) AS average_price,
    ROUND(average_price_per_sqm, 2) AS average_price_per_sqm
FROM ranked_towns
ORDER BY price_rank, town_name;