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
Test-Path (Join-Path $DATA_PATH 'data\raw')
Test-Path (Join-Path $RELEASE_PATH 'manifest.json')
Test-Path (Join-Path $MARIADB_PATH 'load_mariadb.py')
Test-Path (Join-Path $MARIADB_PATH 'requirements.txt')
Test-Path (Join-Path $MONGODB_PATH 'scripts\setup_mongodb.py')
```

Each command should return `True`. If one returns `False`, correct that path or restore the missing files before continuing.

## 3. Make the data available to the MariaDB loader

The MariaDB loader looks for the files in `data\raw` and `data\processed` **under `MARIADB_PATH`**. Your shared data folder can stay separate, but the MariaDB folder must have access to the same data in that layout.

First check whether the MariaDB folder already has the data:

```powershell
Test-Path (Join-Path $MARIADB_PATH 'data\raw')
Test-Path (Join-Path $MARIADB_PATH "data\processed\$RELEASE_ID\manifest.json")
```

If both results are `True`, confirm that these are the same raw files and release as the `DATA_PATH` copy. If either is `False`, and there is no existing `data` folder inside `MARIADB_PATH`, create a directory link to the `data` folder inside `DATA_PATH`:

```powershell
$DATA_CONTENTS = Join-Path $DATA_PATH 'data'
$MARIADB_DATA = Join-Path $MARIADB_PATH 'data'
New-Item -ItemType Junction -Path $MARIADB_DATA -Target $DATA_CONTENTS
```

If `MARIADB_PATH\data` already exists but is incomplete, stop and compare its contents before changing it. Do not overwrite an existing data folder or junction blindly.

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
mariadb -u root -p
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

At the MariaDB prompt, run SQL files `01` through `06` in order. For each `SOURCE` command below, replace `MARIADB_PATH` with the actual full folder path. Use forward slashes in the path. For example, a Windows folder `C:\Work Files\MariaDB` becomes `C:/Work Files/MariaDB`.

```sql
SOURCE MARIADB_PATH/sql/01_reference_tables.sql;
SOURCE MARIADB_PATH/sql/02_category_tables.sql;
SOURCE MARIADB_PATH/sql/03_resale_table.sql;
SOURCE MARIADB_PATH/sql/04_flat_type_demographics.sql;
SOURCE MARIADB_PATH/sql/05_ethnicity_demographics.sql;
SOURCE MARIADB_PATH/sql/06_mobility_and_metadata.sql;
```

If MariaDB cannot read a path containing spaces, use the MariaDB client's quoted file-path form, for example `SOURCE "C:/Work Files/MariaDB/sql/01_reference_tables.sql";`.

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
& $PYTHON -m pip install -r (Join-Path $MARIADB_PATH 'requirements-mariadb.txt')
```

The second requirements file adds the MariaDB Python connector needed by the loader. It is a dependency declaration, not a tested version lock. Record the connector version that pip installs and the Python version used for the setup.

Run the MariaDB loader:

```powershell
& $PYTHON (Join-Path $MARIADB_PATH 'load_mariadb.py')
```

Enter the local `hdb_dev` password when prompted. The loader checks the raw and prepared files and the database tables. It expects empty analytical tables and commits only after its checks pass. **Do not run the initial loader against a database that already contains the analytical release.** If this is not a fresh database, stop and agree on the reload procedure with the database owner.

## 8. Add MariaDB demo data and application permissions

Connect to MariaDB as an administrator again:

```powershell
mariadb -u root -p
```

Run these three scripts in order, replacing `MARIADB_PATH` with the actual path as in Step 6:

```sql
SOURCE MARIADB_PATH/sql/16_demo_reference_tables.sql;
SOURCE MARIADB_PATH/sql/17_demo_resale_table.sql;
SOURCE MARIADB_PATH/sql/18_demo_seed_data.sql;
```

Check the script's results. They should show **26 towns, 7 flat types, 10 matching seed rows, and 0 demo transactions**. If all four match, enter `COMMIT;` in that same session. If any result differs, enter `ROLLBACK;` and stop to investigate.

Then run the demo protections and application permission script:

```sql
SOURCE MARIADB_PATH/sql/19_demo_lineage_protection.sql;
SOURCE MARIADB_PATH/sql/24_application_permissions.sql;
```

Run script `24` as `root` or another authorized administrator. The app will use `hdb_app`, not `hdb_dev`.

## 9. Set up and load MongoDB

In PowerShell, set the MongoDB connection for this window and run the setup and connection check:

```powershell
$env:MONGODB_URI = 'mongodb://127.0.0.1:27017/'
$env:MONGODB_DATABASE = 'hdb_insights'
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\setup_mongodb.py') --create-missing --create-demo
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\check_mongodb.py')
```

Validate the prepared release without writing it to MongoDB:

```powershell
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\load_mongodb.py') --release-dir $RELEASE_PATH --dry-run
```

Continue only if the dry run succeeds. For a new, empty target database, stop the application and publish the release:

```powershell
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\load_mongodb.py') --release-dir $RELEASE_PATH --publish --maintenance-confirmed
```

Keep the recovery journal created by the loader. Do not load, publish, recover, or reset against an already populated database without coordinating with its owner. A successful load on another person's computer does not prove this MongoDB server has been loaded.

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
& $PYTHON -m pytest -q (Join-Path $APPLICATION_PATH 'tests\test_person_d.py')
& $PYTHON (Join-Path $APPLICATION_PATH 'scripts\check_adapter_contracts.py')
& $PYTHON (Join-Path $APPLICATION_PATH 'scripts\verify_prepared_release.py')
& $PYTHON (Join-Path $MARIADB_PATH 'verify_mariadb_release.py')
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\check_mongodb.py')
& $PYTHON (Join-Path $MONGODB_PATH 'scripts\smoke_mongodb.py')
```

The MariaDB verifier needs both the original raw files and the prepared release, and may prompt for a database password. The MongoDB smoke check is read-only unless explicitly given `--demo-crud`.

Finally, open each backend in the app and check overview, resale, demographics, mobility, comparison, and demo create/read/update/delete. Use only the demo area for CRUD; after deleting a test demo record, confirm the analytical resale row count has not changed. Record the Python, MariaDB, MongoDB, and connector versions and the actual results from this computer. Confirm any remaining team decisions about dropdown options, missing mobility behavior, and demo seed selection before calling the setup complete.
