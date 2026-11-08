# Person B — MariaDB handover, review revision B-2026-10-31-01

Contract: HDBI-1.0.0. Data: 150921447b27_c1.0.0_t0.1.2.
Owner: Ho Chang Rong (CR). A Xavier: data; C Isaac: MongoDB; D Bill: API/Streamlit; E Xi Fa: QA/equivalence.

## Current status and evidence limits

CR reported successful laptop runs of the six analytical repository functions and the complete demo CRUD suite on 31 October 2026. Earlier supplied output verifies 240,468 resale rows, six demographic tables (63/21/18/45/15/12 rows), 1,440 mobility rows, and 73 unresolved mobility counts retained as NULL. The final CRUD checks cover create/read/update/no-op update, invalid edits, delete/not-found, and an unchanged analytical seed and resale row count. They do not prove every analytical value stayed unchanged.

This review preserved the working adapter, connection module, loader and SQL byte-for-byte. It removed cache files and backup copies from the distribution, not from CR's laptop. Added: this guide, requirements-mariadb.txt, and verify_mariadb_release.py. Existing README.md remains A's preparation guide.

Review-time checks: all Python source files compile; the new comparison helper rejects changed values and duplicate-count differences. No live MariaDB is available in the review environment. The new verifier has NOT yet passed against CR's database. Review-environment pytest was unavailable; A's historical passing results are not represented as a fresh run here.

## CR: apply without rebuilding

Copy the contents of this ZIP into the existing project root, alongside load_mariadb.py. Keep the existing data folder. The ZIP intentionally excludes raw/processed CSVs, passwords, virtualenvs, pyc files and backup files.

Do NOT rerun schema scripts or the loader on the working database. Use the existing virtualenv and run this new read-only reconciliation once:

```powershell
& "$env:USERPROFILE\.venvs\hdb-insights\Scripts\python.exe" .\verify_mariadb_release.py
```

Enter the hdb_app password (blank is supported). This verifies the raw/output hashes, every field of all eight loaded datasets including duplicate multiplicity, analytical lookup values, and release metadata. It records remaining demo IDs but deletes nothing. Evidence: docs/evidence/B/release_verification.json. Send that JSON to central coordination; it supplies the IDs needed to identify the failed-run leftover and the installed MariaDB connector version.

Do not repeat already-passing CRUD/analytics tests unless relevant code changes or integration exposes a failure. The verifier requires A's original raw files and the exact prepared release in the existing data directory.

## Setup on a NEW teammate machine only

1. Obtain A's original raw files under data/raw and the prepared release under data/processed/150921447b27_c1.0.0_t0.1.2 (including manifest.json). The loader checks both sets of bytes. Copying code does not copy database records.
2. Create a Python virtualenv. Install A's requirements.txt and the extra requirements-mariadb.txt. The latter declares the previously missing driver; it is not a tested version lock. Prefer CR's recorded connector version once the verifier reports it. The original pytest upper bound (<9) differs from CR's previously reported pytest 9.2.0; agree and capture the final environment before reproducibility sign-off. Do not downgrade CR's working environment for this review.
3. Install/start MariaDB. CR's observed version is 12.3.3; Python 3.14.5. Teammate installation is unverified.
4. As administrator, create the two databases and local accounts below on a fresh machine. Substitute locally chosen passwords before executing. Do not commit real passwords. CR need not run any of this.

```sql
CREATE DATABASE hdb_insights CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE DATABASE hdb_insights_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER 'hdb_dev'@'localhost' IDENTIFIED BY 'REPLACE_LOCALLY';
CREATE USER 'hdb_app'@'localhost' IDENTIFIED BY 'REPLACE_LOCALLY';
GRANT ALL PRIVILEGES ON hdb_insights.* TO 'hdb_dev'@'localhost';
GRANT ALL PRIVILEGES ON hdb_insights_demo.* TO 'hdb_dev'@'localhost';
```

5. In MariaDB client, SOURCE sql/01 through sql/06 in numeric order using each full absolute path. These create the 14 analytical tables. Existing-table errors mean stop and inspect, not blindly continue. For example: `SOURCE C:/project/hdb-insights/sql/01_reference_tables.sql` (replace with actual path).
6. From project-root PowerShell run `python .\load_mariadb.py`. This loader connects locally as hdb_dev and prompts for its password. All analytical tables must be empty. It validates before loading and commits only after integrity/count checks. It deliberately refuses populated databases. For an existing release use the verifier, not a second import. Automated replacement of a different release is not implemented; do not truncate to force a reload.
7. SOURCE sql/12_monthly_resale_view.sql for the optional SQL demonstration view. The Python adapter does not depend on this view.
8. SOURCE sql/16_demo_reference_tables.sql then sql/17_demo_resale_table.sql. SOURCE sql/18_demo_seed_data.sql; inspect 26 towns, 7 flat types, 10 matching seeds, 0 demo transactions; then COMMIT in that same session. If incorrect, ROLLBACK. SOURCE sql/19_demo_lineage_protection.sql.
9. As administrator SOURCE sql/24_application_permissions.sql after creating hdb_app. It adds intended grants; it does not revoke older excess grants on reused accounts. Use fresh accounts or independently review effective privileges. Keep application writes restricted to the demo table and its business columns.
10. Run the read-only verifier. Then the team integration suite against the selected backend. Do not run all numbered SQL files as a setup batch.

## Script classification

| Files | Purpose | Normal application startup? |
|---|---|---|
| sql/01–06 | One-time analytical DDL | No |
| load_mariadb.py | Initial, empty-database import | No |
| sql/12 | Optional monthly-summary demonstration view | No |
| sql/16–19 | One-time demo schema, seed provisioning, triggers | No |
| sql/24 | Administrator grants | No |
| sql/07–11,13–15 | Query examples, plans and diagnostics | No |
| sql/20–23 | Historical manual CRUD exercises, including deliberate failures and fixed IDs | No |
| check_*.py | Development verification; some create/delete demo records | No |
| verify_mariadb_release.py | Read-only full-value reconciliation and inventory | On handover/release changes |
| src/hdb_insights/db/*.py | Runtime adapter and connection factory | Imported by application |

## Bill: runtime integration

Run the app from project root and import:

```python
from src.hdb_insights.db import mariadb_repository as db
```

The repository uses module-level functions, not a class. It opens/closes a connection per call and has no interactive password prompts. Configure MARIADB_PASSWORD in the app process before calling it. An empty string is valid; an absent variable is an error. Defaults: host 127.0.0.1, port 3306, user hdb_app, database hdb_insights. Other optional variables: MARIADB_HOST, MARIADB_PORT, MARIADB_USER, MARIADB_DATABASE. Demo operations explicitly reference hdb_insights and hdb_insights_demo; arbitrary database renaming is NOT supported by changing MARIADB_DATABASE alone.

Never use the loader's privileged hdb_dev account for Streamlit. Never cache live connections. If caching returned data, key by backend/release/filters and invalidate demo results after writes.

Every result has ok,data,error,meta. Check ok before consuming data. Error codes: VALIDATION_ERROR, NOT_FOUND, CONFLICT, DATA_NOT_READY, DB_UNAVAILABLE, INTERNAL_ERROR. Decimal values are strings with two places; null is None; counts are integers. Convert only for display, not to replace database aggregates. An ambiguous write-connection failure must be investigated before retrying Create: no idempotency token is implemented.

| Function | Data result |
|---|---|
| search_resale(filters,limit=50,offset=0) | rows,total_count,limit,offset; month then record_id order |
| summarise_resale(filters) | transaction_count,average_price,average_price_per_sqm |
| resale_trend(filters) | rows of registration_month,count and averages |
| demographic_profile(group_type,group_code,survey_year) | group_type,group_code,survey_year,average_age,median_age,population_15_plus,population_status,age_distribution,source_rows |
| mobility_breakdown(workplace_area,residence_region_code,survey_year=2020) | rows,published_total,note |
| list_filter_options(domain) | options (see provisional nesting below) |
| create_demo_resale(payload) | stored demo record with generated demo:<UUID> |
| get_demo_resale(demo_record_id) | stored record or NOT_FOUND |
| update_demo_resale(demo_record_id,changes) | updated record; no-op success; empty changes rejected |
| delete_demo_resale(demo_record_id) | deleted_count=1 or NOT_FOUND |

Resale filters: town_name,flat_type_code,start_month,end_month; omitted/None=no restriction. Use None, not ALL, for all resale flat types. Pagination limit 1–500, offset>=0. Mean price/sqm is AVG(each price/area), not a ratio of totals. Empty summary has count=0 and null averages; empty trend has rows=[].

Demographic groups: flat_type or ethnicity. ALL is a published aggregate; absent profiles return ok=true,data=null and a meta note. ALL population stays null/not_provided. Age order BELOW_15,AGE_15_64,AGE_65_PLUS. Source rows sorted by dataset_id/source_row_number. Do not sum population over age groups or infer a town relationship.

Mobility returns four non-ALL modes in the agreed order. Share uses the exact workplace/region/year's published ALL-mode denominator; unresolved and zero-denominator shares stay null. Missing/incomplete selections currently return DATA_NOT_READY. Preserve source rounding differences. Do not join workplace categories to resale towns.

### Proposed dropdown nesting — coordinate with C/D before freezing

- resale options: town_names list[str], flat_types list[{flat_type_code,display_label}], registration_months list[str].
- demographic options: profiles list[{group_type,group_code,display_label,survey_year}]. Filter these combinations to build dependent dropdowns.
- mobility options: selections list[{workplace_area,residence_region_code,survey_year}].

These exact nested names were not fixed in the original C05 briefing. This package implements the proposal locally; it is not evidence that Isaac/Bill have adopted it. Record one central decision before merging both adapters.

### Demo payload and seed restriction

Create requires seed_record_id plus registration_month,town_name,flat_type_code,block,street_name,storey_lower,storey_upper,floor_area_sqm,flat_model,lease_commence_year,remaining_lease_months,resale_price. Price/area accept decimal strings, Decimal or integers (not float); precision beyond two places is rejected. Integers reject bool. Update accepts a non-empty subset of the twelve business fields. Identity, record_kind, seed and release are immutable. Stored output uses town_name, not the internal town_id.

CURRENT LIMITATION: only the first ten source records ORDER BY record_id are registered in demo_seed. Creating from another valid analytical record returns DATA_NOT_READY. Do not grant the application seed-write privileges to bypass this. C/D/E must agree on the same seed selection, or B/C must add a coordinated privileged provisioning process before the UI offers other seeds. Current code does not provide a demo seed-selection/list API. Demo writes are never part of analytical benchmarks.

## Evidence, traceability and remaining work

| Artifact | Purpose | Verification available | Remaining |
|---|---|---|---|
| B-01 sql/01–06 + loader | Eight-dataset relational model/load | CR's counts/NULL/FK checks | New full-value report; fresh-machine reproduction |
| B-02 repository analytical functions | F01,F02,F03; C05 | CR reports all local function tests passed | C/E equivalence and Streamlit flow |
| B-03 demo DDL/triggers/grants + CRUD | CAP01; identity/provenance isolation | CR reports full CRUD suite passed | Inspect failed-run leftover; shared seed policy |
| B-04 sql/12–14 | View, advanced ranking, index evidence | Earlier EXPLAIN selected town/type/month range index | Controlled benchmarks, not terminal timings |
| B-05 verifier + this guide | Reproducible handover | Syntax/helper checks here | Actual laptop verifier output |

Report screenshots/logs are not all contained in this ZIP; preserve CR's session log and existing screenshots separately. No benchmark winner or Excellent-grade claim is justified yet. Existing A traceability.csv is A-owned; merge the B artifact entries into the team's authoritative requirement-ID mapping rather than inventing rubric IDs.

Return progress to central coordination with: owner; package/contract/release revision; changed files/functions; completed/outstanding work; affected interfaces; actual test command/environment/result/evidence; unresolved decisions; proposed shared changes; integration-ready artifacts. Bill owns app wiring, Isaac matching MongoDB responses, Xi Fa independent equality/benchmark evidence. Final report should explain keys/normalisation, Mongo document tradeoffs, constraints, SQL plans, source limitations, actual comparison methodology/results, CRUD isolation, setup/user guide and demonstration flow.

Remaining cleanup: the failed CRUD run committed a row before Update raised NameError and Delete cleanup also failed. Its ID is unknown. The new verifier lists remaining rows. Reconcile those IDs before deleting; do not issue blanket DELETE or TRUNCATE. The successful suite removed only its own fresh row and the earlier saved Create-test row.
