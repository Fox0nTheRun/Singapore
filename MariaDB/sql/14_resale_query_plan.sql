USE hdb_insights;

-- Confirm the indexes currently defined.
SHOW INDEX FROM resale_transaction;

-- Inspect the execution plan for the filtered resale search.
EXPLAIN
SELECT
    r.record_id,
    r.registration_month,
    t.town_name,
    r.flat_type_code,
    r.floor_area_sqm,
    r.resale_price
FROM resale_transaction AS r
JOIN town AS t
    ON t.town_id = r.town_id
WHERE t.town_name = 'ANG MO KIO'
  AND r.flat_type_code = '4_ROOM'
  AND r.registration_month BETWEEN '2020-01' AND '2020-12'
ORDER BY
    r.registration_month,
    r.record_id
LIMIT 20 OFFSET 0;