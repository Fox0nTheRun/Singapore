# HDB Insights setup guide

This guide uses four separate folders: `Application`, `Data`, `MariaDB`, and `MongoDB`. Replace the example placeholders with the full locations on your computer. Do not type the angle brackets around a placeholder.

## 1. Check the four folders

Before setup, make sure you have these files:

| Folder | What it should contain |
|---|---|
| `APPLICATION_PATH` | `app.py`, `src`, `requirements-app.txt`, and the app's `scripts` and `tests` folders |
| `DATA_PATH` | A `data\raw` folder and `data\processed\150921447b27_c1.0.0_t0.1.2` |
| `MARIADB_PATH` | `load_mariadb.py`, `verify_mariadb_release.py`, and the `sql` folder |
| `MONGODB_PATH` | MongoDB scripts under `scripts` and MongoDB source code under `src` |

The prepared release must contain `manifest.json` and all eight prepared CSV files. Keep the filenames and file contents unchanged. Do not import the spreadsheets or CSV files manually through a database GUI; the loaders check the files and their recorded hashes.

Do not put passwords, `.env` files, virtual environments, database server files, or Python caches in a shared ZIP or GitHub repository. Keep a copy of the original raw files and the prepared release.

## 2. Set your folder locations in PowerShell

Open PowerShell and set these four values to the actual locations where you saved the folders. Example values below are placeholders; replace each one.

```powershell
$APPLICATION_PATH = 'C:\path\to\Application'
$DATA_PATH = 'C:\path\to\Data'
$MARIADB_PATH = 'C:\path\to\MariaDB'
$MONGODB_PATH = 'C:\path\to\MongoDB'
$RELEASE_ID = '150921447b27_c1.0.0_t0.1.2'
$RELEASE_PATH = Join-Path $DATA_PATH "data\processed\$RELEASE_ID"
$PYTHON = Join-Path $APPLICATION_PATH '.venv\Scripts\python.exe'
```

Check that the paths point to the right places:

```powershell
Test-Path (Join-Path $APPLICATION_PATH 'app.py')
Test-Path (Join-Path $MARIADB_PATH 'load_mariadb.py')
Test-Path (Join-Path $MARIADB_PATH 'requirements.txt')
Test-Path (Join-Path $MONGODB_PATH 'scripts\setup_mongodb.py')
```

Each command should return `True`. If one returns `False`, correct that path or restore the missing files before continuing.

## 3. Make the data available to the MariaDB loader

The MariaDB loader looks for the files in `data\raw` and `data\processed` **under `MARIADB_PATH`**. Keep the shared `DATA_PATH` folder independent: copy its `data` contents into MariaDB's own `data` folder. Do not create a junction or other link. Changes made to MariaDB's copy will then not change the shared data files.

Set the source and destination paths, then copy the files:

```powershell
$DATA_CONTENTS = Join-Path $DATA_PATH 'data'
$MARIADB_DATA = Join-Path $MARIADB_PATH 'data'
New-Item -ItemType Directory -Path $MARIADB_DATA -Force | Out-Null
Copy-Item -Path (Join-Path $DATA_CONTENTS '*') -Destination $MARIADB_DATA -Recurse -Force
```

`Copy-Item` copies from `DATA_PATH` into `MARIADB_PATH`; it does not link the folders. If a same-named file already exists in the MariaDB copy, it is replaced by the source copy. The source files in `DATA_PATH` are not changed. After copying, verify that the raw folder and prepared release are present:

```powershell
Test-Path (Join-Path $MARIADB_DATA 'raw')
Test-Path (Join-Path $MARIADB_DATA "processed\$RELEASE_ID\manifest.json")
```

Both checks should return `True`. Rerun the copy command after updating the shared release so the MariaDB copy has the same files.

## 4. Install and start the database servers

Install MariaDB Server and MongoDB Server on this computer. MongoDB Compass is only a client; the MongoDB Server must also be installed and running.

In PowerShell, check the services:

```powershell
Get-Service *MariaDB*
Get-Service *Mongo*
```

If a service is stopped, start it using the service name shown on your computer. For example:

```powershell
Start-Service -Name MariaDB
Start-Service -Name MongoDB
```

Service names can differ by installation. CR recorded MariaDB 12.3.3 on port 3306. Record the versions and ports actually installed on this computer. The team should agree on one Python version before calling the setup reproducible.

## 5. Create the MariaDB databases and accounts

Open a MariaDB client as an administrator from PowerShell:

```powershell
.\mariadb -u root -p
```

At the `MariaDB>` prompt, create the databases and users. Before running the SQL, replace both password placeholders with passwords chosen for this computer. Do not use a password from a handover document, and do not commit the passwords.

```sql
CREATE DATABASE hdb_insights CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE DATABASE hdb_insights_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

CREATE USER 'hdb_dev'@'localhost' IDENTIFIED BY 'CHOOSE_LOCAL_DEV_PASSWORD';
CREATE USER 'hdb_app'@'localhost' IDENTIFIED BY 'CHOOSE_LOCAL_APP_PASSWORD';

GRANT ALL PRIVILEGES ON hdb_insights.* TO 'hdb_dev'@'localhost';
GRANT ALL PRIVILEGES ON hdb_insights_demo.* TO 'hdb_dev'@'localhost';
```

The loader uses `hdb_dev`. The application uses the less privileged `hdb_app` account; its permissions are granted later in Step 8.

## 6. Create the MariaDB analytical tables

At the MariaDB prompt, run SQL files `01` through `06` in order. Replace `YOUR_MARIADB_FOLDER` in each command with the full path to the folder that contains `sql`. This is a placeholder; MariaDB will not fill it in automatically. Use forward slashes. For example, if the folder is `C:\Work Files\MariaDB`, enter `C:/Work Files/MariaDB` in place of `YOUR_MARIADB_FOLDER`.

```sql
SOURCE YOUR_MARIADB_FOLDER/sql/01_reference_tables.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/02_category_tables.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/03_resale_table.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/04_flat_type_demographics.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/05_ethnicity_demographics.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/06_mobility_and_metadata.sql;
```

Do not type `YOUR_MARIADB_FOLDER` literally or put quotes around the path. For example, with `C:/Work Files/MariaDB`, the first command is `SOURCE C:/Work Files/MariaDB/sql/01_reference_tables.sql;`.

These are one-time schema setup scripts for a fresh database. If a script says a table already exists or any step fails, stop and inspect the database; do not keep running the remaining scripts or rerun them after an ordinary code update.

## 7. Create the application Python environment and load MariaDB

Exit the MariaDB client:

```sql
EXIT;
```

Back in PowerShell, create the app's virtual environment and install its requirements. These commands use the path you set in Step 2 and do not require activating the environment:

```powershell
Set-Location -LiteralPath $APPLICATION_PATH
py -m venv .venv
& $PYTHON -m pip install -r (Join-Path $APPLICATION_PATH 'requirements-app.txt')
& $PYTHON -m pip install -r (Join-Path $MARIADB_PATH 'requirements.txt')
```

The second requirements file adds the MariaDB Python connector needed by the loader. It is a dependency declaration, not a tested version lock. Record the connector version that pip installs and the Python version used for the setup.

Run the MariaDB loader:

```powershell
& $PYTHON (Join-Path $MARIADB_PATH 'load_mariadb.py')
```

Enter the local `hdb_dev` password when prompted. The loader checks the raw and prepared files and the database tables. It expects empty analytical tables and commits only after its checks pass. **Do not run the initial loader against a database that already contains the analytical release.** If this is not a fresh database, stop and agree on the reload procedure with the database owner.

This Python loader populates the analytical database, `hdb_insights`; it does **not** populate `hdb_insights_demo`. To load the demo seed data into `hdb_insights_demo`, continue with Step 8. The demo data load is the `18_demo_seed_data.sql` script, which must run after the two demo table scripts (`16` and `17`).

### Optional analytical queries after Step 7

Once the analytical release is loaded, run the relevant command at the MariaDB prompt when checking results or preparing a demonstration. Finish any open transaction first. Script 12 creates a persistent view and should run only when that view is absent.

| Script | When to run |
|---|---|
| `SOURCE YOUR_MARIADB_FOLDER/sql/07_resale_search.sql;` | Search resale records |
| `SOURCE YOUR_MARIADB_FOLDER/sql/08_resale_summary_trend.sql;` | Check resale summaries and monthly trends |
| `SOURCE YOUR_MARIADB_FOLDER/sql/09_demographic_flat_profile.sql;` | Inspect a demographic profile by flat type |
| `SOURCE YOUR_MARIADB_FOLDER/sql/10_demographic_ethnicity_profile.sql;` | Inspect a demographic profile by ethnicity |
| `SOURCE YOUR_MARIADB_FOLDER/sql/11_mobility_breakdown.sql;` | Inspect a mobility breakdown |
| `SOURCE YOUR_MARIADB_FOLDER/sql/12_monthly_resale_view.sql;` | Create and verify the monthly resale summary view |
| `SOURCE YOUR_MARIADB_FOLDER/sql/13_resale_town_ranking.sql;` | Rank towns by resale activity |
| `SOURCE YOUR_MARIADB_FOLDER/sql/14_resale_query_plan.sql;` | Inspect indexes and the resale query plan |
| `SOURCE YOUR_MARIADB_FOLDER/sql/15_loaded_data_checks.sql;` | Validate the loaded tables and reference data |

## 8. Add MariaDB demo data and application permissions

After the MariaDB loader finishes successfully, run the demo setup commands below. These commands are entered at the MariaDB prompt, not in PowerShell. Replace `YOUR_MARIADB_FOLDER` with the full path to your MariaDB folder, using forward slashes. Do not type the placeholder literally or put quotes around the path.

Connect to MariaDB as an administrator again:

```powershell
.\mariadb -u root -p
```

At the `MariaDB>` prompt, run these three scripts in order. The third command loads the demo seed data into `hdb_insights_demo`:

```sql
SOURCE YOUR_MARIADB_FOLDER/sql/16_demo_reference_tables.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/17_demo_resale_table.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/18_demo_seed_data.sql;
```

Check the script's results. They should show **26 towns, 7 flat types, 10 matching seed rows, and 0 demo transactions**. If any result differs or an insert failed, enter `ROLLBACK;` and stop. If all counts match and all inserts succeeded, finish the seed transaction in the same session before running script 19.

```sql
COMMIT;
```


Then run the demo protections and application permission script:

```sql
SOURCE YOUR_MARIADB_FOLDER/sql/19_demo_lineage_protection.sql;
SOURCE YOUR_MARIADB_FOLDER/sql/24_application_permissions.sql;
```

Run script `24` as `root` or another authorized administrator. The app will use `hdb_app`, not `hdb_dev`.

### Optional MariaDB demo CRUD walkthrough (scripts 20–23)

Run this once after Step 8 when demonstrating create, read, update, identity protection, price validation, and delete. Normal application startup can skip this walkthrough. Use one MariaDB client session throughout, connected as the local development account with access to both databases so the identity test reaches the trigger. Replace the folder placeholder as in Step 6.

**20 — Create and read one demo record.** The script generates a new ID, starts a transaction, inserts the row and reads it back.

```sql
SOURCE YOUR_MARIADB_FOLDER/sql/20_demo_create_read.sql;
```

If the script displays exactly one new demo row, save it for the next test. If creation failed, use `ROLLBACK;` and stop.

```sql
COMMIT;
```

**21–23 — Use the ID created by script 20.** The distributed files set `@demo_id` to a fixed example ID. Run the blocks below at the MariaDB prompt in place of sourcing those three files. They retain the generated session ID and put the savepoints inside the relevant transactions. Execute one block at a time and inspect its output before continuing.

**21 — Update the demo price.** Run the first block and confirm the locked row has the ID returned by script 20. If there is no row, run `ROLLBACK;` and stop.

```sql
USE hdb_insights_demo;


START TRANSACTION;

-- Read and lock the selected demo record.
SELECT demo_record_id, resale_price AS price_before
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id
FOR UPDATE;
```

Set a savepoint before the update.

```sql
SAVEPOINT before_demo_update;
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
```

If the demo price is 240000.00 and the analytical source price is unchanged, finish the update.

```sql
COMMIT;
```

If the check fails, undo the update and end the transaction instead.

```sql
ROLLBACK TO SAVEPOINT before_demo_update;
ROLLBACK;
```

**22 — Test identity protection.** Confirm `target_rows = 1` before proceeding.

```sql
USE hdb_insights_demo;

SET @attempted_id = CONCAT('demo:', UUID());

START TRANSACTION;

-- Confirm that the target exists before testing.
SELECT COUNT(*) AS target_rows
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;
```

The next update should raise the identity-protection trigger error.

```sql
-- EXPECTED ERROR: the trigger must reject this identity change.
UPDATE demo_resale_transaction
SET demo_record_id = @attempted_id
WHERE demo_record_id = @demo_id;
```

In the same session, check for one original ID and zero attempted IDs before the rollback. If the update succeeded unexpectedly, stop after the rollback.

```sql
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
```

**23A — Test invalid-price rejection.** Confirm the starting price is 240000.00.

```sql
USE hdb_insights_demo;

-- PART A: Reject an invalid price.
START TRANSACTION;

SELECT resale_price AS price_before
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;
```

Run the invalid update and expect a price constraint error.

```sql
-- EXPECTED ERROR: chk_demo_price must reject this.
UPDATE demo_resale_transaction
SET resale_price = -1.00
WHERE demo_record_id = @demo_id;
```

Check for PASS before rolling back. Continue to deletion only if the update was rejected and the price stayed unchanged.

```sql
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
```

**23B — Delete the demo row.** This transaction removes the record created in script 20.

```sql
START TRANSACTION;
SAVEPOINT before_demo_delete;

DELETE FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

SELECT ROW_COUNT() AS deleted_rows;

SELECT COUNT(*) AS remaining_demo_rows
FROM demo_resale_transaction
WHERE demo_record_id = @demo_id;

-- Original analytical data must still exist.
SELECT COUNT(*) AS analytical_resale_rows
FROM hdb_insights.resale_transaction;
```

If `deleted_rows = 1`, `remaining_demo_rows = 0`, and the analytical resale count still matches the loaded release (240,468 for the supplied release), confirm the deletion.

```sql
COMMIT;
```

To undo the deletion instead, run this before committing.

```sql
ROLLBACK TO SAVEPOINT before_demo_delete;
ROLLBACK;
```

## 9. Set up and load MongoDB

In PowerShell, set the MongoDB connection for this window and run the setup and connection check:

```powershell
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017/'
$env:MONGODB_DATABASE = 'hdb_insights'
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\setup_mongodb.py') --create-missing --create-demo
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\check_mongodb.py')
```

The `--create-demo` option creates the MongoDB demo collection. There is no separate command that preloads demo transaction rows: demo rows are created from a loaded resale seed when you use the app's demo CRUD feature. Load and publish the analytical release first so a resale seed is available.

Validate the prepared release without writing it to MongoDB:

```powershell
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\load_mongodb.py') --release-dir $RELEASE_PATH --dry-run
```

Continue only if the dry run succeeds. For a new, empty target database, stop the application and publish the release:

```powershell
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\load_mongodb.py') --release-dir $RELEASE_PATH --publish --maintenance-confirmed
```

## 10. Configure and start the application

Use the same PowerShell window. Set the MariaDB app password to the local password chosen in Step 5; set the other values to match your local server configuration:

```powershell
$env:MARIADB_HOST = '127.0.0.1'
$env:MARIADB_PORT = '3306'
$env:MARIADB_USER = 'hdb_app'
$env:MARIADB_DATABASE = 'hdb_insights'
$env:MARIADB_PASSWORD = 'YOUR_LOCAL_APP_PASSWORD'
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017/'
$env:MONGODB_DATABASE = 'hdb_insights'
```

The values are temporary and apply only to this PowerShell window. Keep it open, move to the application folder, and start the app:

```powershell
Set-Location -LiteralPath $APPLICATION_PATH
& $PYTHON -m streamlit run (Join-Path $APPLICATION_PATH 'app.py')
```

Open the local address printed by Streamlit, usually `http://localhost:8501`. For the comparison page, both databases must have the same active contract (`HDBI-1.0.0`) and release (`150921447b27_c1.0.0_t0.1.2`).

## 11. Verify the setup

With the app environment and database services available, run the checks from PowerShell. These commands are examples of checks included in the handover packages; run only those files that are present in the corresponding folder.

```powershell
Set-Location -LiteralPath $APPLICATION_PATH
& $PYTHON -m pytest -q (Join-Path $APPLICATION_PATH 'tests\test_application.py')
& $PYTHON (Join-Path $APPLICATION_PATH 'scripts\check_adapter_contracts.py')
& $PYTHON (Join-Path $APPLICATION_PATH 'scripts\verify_prepared_release.py') --release-dir $RELEASE_PATH
& $PYTHON (Join-Path $MARIADB_PATH 'verify_mariadb_release.py')
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\check_mongodb.py')
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\smoke_mongodb.py')
```

The MariaDB verifier needs both the original raw files and the prepared release, and may prompt for a database password. The MongoDB smoke check is read-only unless explicitly given `--demo-crud`.

To check MongoDB demo CRUD, first confirm that the analytical release is loaded and the demo collection was created in Step 9. Then run this optional lifecycle check:

```powershell
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\smoke_mongodb.py') --demo-crud
```

This check creates a temporary demo record from a resale seed, reads and updates it, then deletes it and confirms the analytical resale summary is unchanged. Run it only against the intended local demo database. Do not use a shared or production database.

Finally, open each backend in the app and check overview, resale, demographics, mobility, comparison, and demo create/read/update/delete. Use only the demo area for CRUD; after deleting a test demo record, confirm the analytical resale row count has not changed. Record the Python, MariaDB, MongoDB, and connector versions and the actual results from this computer. Confirm any remaining team decisions about dropdown options, missing mobility behavior, and demo seed selection before calling the setup complete.

