-- HDB Insights | HDBI-1.0.0
-- F01 Resale Explorer: filtered search
USE hdb_insights;

-- Example filters; month endpoints are inclusive.
SET @filter_town = 'ANG MO KIO';
SET @filter_flat_type = '4_ROOM';
SET @start_month = '2020-01';
SET @end_month = '2020-12';

-- Count all matching records.
SELECT COUNT(*) AS total_matches
FROM resale_transaction AS r
JOIN town AS t ON t.town_id = r.town_id
WHERE t.town_name = @filter_town
  AND r.flat_type_code = @filter_flat_type
  AND r.registration_month BETWEEN @start_month AND @end_month;

-- Show the first 20 matching records.
SELECT
    r.record_id,
    r.registration_month,
    t.town_name,
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
FROM resale_transaction AS r
JOIN town AS t ON t.town_id = r.town_id
WHERE t.town_name = @filter_town
  AND r.flat_type_code = @filter_flat_type
  AND r.registration_month BETWEEN @start_month AND @end_month
ORDER BY r.registration_month, r.record_id
LIMIT 20 OFFSET 0;