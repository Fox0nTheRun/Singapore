# Isaac original MongoDB handover — confirmation for Person D

Original upload: `MongoDB_Handover_2026-10-30(1).zip` (55 archive entries, including original modules, scripts, tests, fixtures, and evidence). This revised project contains the original `.py` sources, with original filenames, in `src/hdb_insights/db/`, `scripts/`, and `tests/mongodb/`.

## Verified against the earlier integrated project

- The original `src/hdb_insights/db/mongodb_adapter.py` was an **exact textual match** to the earlier recovered adapter.
- All seven other `src/hdb_insights/db/mongo_*.py` modules contained the same source, differing only by trailing blank lines in the older reconstruction.
- The previously renamed script aliases were removed and replaced by the actual script filenames: `_mongo_bootstrap.py`, `capture_mongodb_plans.py`, `check_mongodb.py`, `load_mongodb.py`, `make_mongodb_fixtures.py`, `recover_mongodb.py`, `reset_mongodb_demo.py`, `setup_mongodb.py`, `smoke_mongodb.py`.
- This revised archive also includes Isaac's original `tests/mongodb/*.py` and explicitly marked `tests/fixtures/TEST_FIXTURE_ONLY` data. These were absent from the prior integrated package.
- The original `requirements-mongodb.txt` is retained under `docs/`. The combined `requirements-app.txt` supplies the intersection of D's chosen dependency ranges and Isaac's PyMongo/pytest requirements.

## Original behavior confirmed from source

`MongoDBAdapter` is a class. Its public methods use `@response`, returning `ok`, `data`, `error`, and `meta` with `backend`, `contract_version`, and `data_release_id`. The 10 operations correspond to Chang Rong's module-level MariaDB functions. Person D's static signature audit reports 20/20 matching public argument sets (after removing MongoDB's injected `self,active`).

The MongoDB constructor accepts an `options_formatter`; `list_filter_options()` returns `DATA_NOT_READY` without it. D injects a formatter that produces CR's proposed `data.options` shape and CR's actual display labels. `missing_mobility_policy` is optional and defaults to `None`: a non-existent mobility profile returns `DATA_NOT_READY` under the current code. The UI only offers data-backed dropdown values and does not override this policy.

The analytics collections are read-only from the frontend. Demo CRUD uses the separate `hdb_insights_demo` collection and checks schema validation and active release metadata. The frontend never runs schema migrations, loaders or recovery by itself.

## What the handover evidence shows — and does not show

Isaac's original `published_load.json` reports **`PUBLISHED`** at `2026-10-29T10:55:18.068247+00:00` for release `150921447b27_c1.0.0_t0.1.2`. Original `smoke_after_load.txt` records successful search, summary, trend, demographic, mobility, create/read/update/delete and subsequent unchanged analytical summary for that earlier run (it is UTF-16 text). The original `server_tests.xml` reports 88 tests, 0 errors, 0 failures and 1 skipped at the time of that run. These are **Isaac's historical output artifacts** and must not be described as a fresh test on this machine or as proof that the final Streamlit integration works.

This revision's own verification is limited to Person D's isolated tests, static signature audit, Python compilation, and processed-data manifest checksum/row-count check. `pymongo`, `mariadb`, `streamlit`, and database servers were not available to this authoring environment. Consequently no live database or browser test was run, and Isaac's original tests could not be executed in this environment.

## Safe test/start sequence on the team's Windows machine

```powershell
# From the integrated project root in a fresh virtual environment:
python -m pip install -r requirements-app.txt
python -m pytest -q tests/test_person_d.py
python scripts/check_adapter_contracts.py
python scripts/verify_prepared_release.py
python -m pytest -q tests/mongodb/test_offline.py tests/mongodb/test_recovery_algorithm.py

# Read-only MongoDB preflight on the *currently configured* server:
python scripts/check_mongodb.py
python scripts/smoke_mongodb.py
```

The final two commands require a running, configured MongoDB and an active published release. `smoke_mongodb.py` does **not** write without `--demo-crud`. Do not run load/publish/recovery/reset scripts on a populated database based only on this guide; consult Isaac and coordinate offline maintenance. MongoDB real-server fixture tests require an explicitly isolated test URI and `HDBI_RUN_MONGO_TESTS=1` and must never target a shared/production collection.

**Team decisions still to finalise:** shared C05 nested filter options with B/C/E, missing-mobility `DATA_NOT_READY` policy, the common first-10-seeds restriction, and independent equivalent-result evidence from Xi Fa.
