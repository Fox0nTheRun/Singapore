USE hdb_insights_demo;

-- ID of the demo record shown in the screenshot.
SET @demo_id = 'demo:4c2427f1-d47b-11f1-b9d9-8c3b4a4a040d';

START TRANSACTION;

-- Read and lock the selected demo record.
SELECT demo_record_id, resale_price AS price_before
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id
FOR UPDATE;

-- Update only this demo record.
UPDATE demo_resale_transaction
SET resale_price = 240000.00
WHERE demo_record_id = @demo_id;

SELECT ROW_COUNT() AS changed_rows;

-- Compare the demo with its original analytical source.
SELECT
    d.resale_price AS demo_price,
    r.resale_price AS source_price,
    CASE
        WHEN d.resale_price = 240000.00
         AND r.resale_price = 232000.00
        THEN 'PASS'
        ELSE 'FAIL'
    END AS result
FROM demo_resale_transaction AS d
JOIN hdb_insights.resale_transaction AS r
    ON r.record_id = d.seed_record_id
WHERE d.demo_record_id = @demo_id;

-- Commit manually after checking the results.