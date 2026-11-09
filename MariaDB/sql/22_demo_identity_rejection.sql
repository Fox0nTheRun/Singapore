USE hdb_insights_demo;

SET @demo_id = 'demo:4c2427f1-d47b-11f1-b9d9-8c3b4a4a040d';
SET @attempted_id = CONCAT('demo:', UUID());

START TRANSACTION;

-- Confirm that the target exists before testing.
SELECT COUNT(*) AS target_rows
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

-- EXPECTED ERROR: the trigger must reject this identity change.
UPDATE demo_resale_transaction
SET demo_record_id = @attempted_id
WHERE demo_record_id = @demo_id;

-- Inspect before rollback so rollback cannot hide a successful change.
SELECT
    (
        SELECT COUNT(*)
        FROM demo_resale_transaction
        WHERE demo_record_id = @demo_id
    ) AS original_id_rows,
    (
        SELECT COUNT(*)
        FROM demo_resale_transaction
        WHERE demo_record_id = @attempted_id
    ) AS attempted_id_rows;

ROLLBACK;

SELECT demo_record_id, resale_price
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;