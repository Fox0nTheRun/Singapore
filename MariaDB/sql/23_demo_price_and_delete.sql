USE hdb_insights_demo;

SET @demo_id = 'demo:4c2427f1-d47b-11f1-b9d9-8c3b4a4a040d';

-- PART A: Reject an invalid price.
START TRANSACTION;

SELECT resale_price AS price_before
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

-- EXPECTED ERROR: chk_demo_price must reject this.
UPDATE demo_resale_transaction
SET resale_price = -1.00
WHERE demo_record_id = @demo_id;

-- Check BEFORE rollback: the rejected update must leave the price intact.
SELECT
    resale_price,
    CASE
        WHEN resale_price = 240000.00 THEN 'PASS'
        ELSE 'FAIL'
    END AS price_rejection_check
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

ROLLBACK;


-- PART B: Delete the demo record.
START TRANSACTION;

DELETE FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

SELECT ROW_COUNT() AS deleted_rows;

SELECT COUNT(*) AS remaining_demo_rows
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

-- Original analytical data must still exist.
SELECT COUNT(*) AS analytical_resale_rows
FROM hdb_insights.resale_transaction;

-- Commit the deletion manually after checking results.