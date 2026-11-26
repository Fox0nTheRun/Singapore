-- Run as root or another authorised administrator.

-- Read analytical tables and views.
GRANT SELECT
ON hdb_insights.*
TO 'hdb_app'@'localhost';

-- Read demo reference data and source lineage.
GRANT SELECT
ON hdb_insights_demo.town
TO 'hdb_app'@'localhost';

GRANT SELECT
ON hdb_insights_demo.flat_type
TO 'hdb_app'@'localhost';

GRANT SELECT
ON hdb_insights_demo.demo_seed
TO 'hdb_app'@'localhost';

-- Create, read and delete editable demo records.
GRANT SELECT, INSERT, DELETE
ON hdb_insights_demo.demo_resale_transaction
TO 'hdb_app'@'localhost';

-- Update business fields only; identity and lineage are excluded.
GRANT UPDATE (
    registration_month,
    town_id,
    flat_type_code,
    block,
    street_name,
    storey_lower,
    storey_upper,
    floor_area_sqm,
    flat_model,
    lease_commence_year,
    remaining_lease_months,
    resale_price
)
ON hdb_insights_demo.demo_resale_transaction
TO 'hdb_app'@'localhost';

SHOW GRANTS FOR 'hdb_app'@'localhost';