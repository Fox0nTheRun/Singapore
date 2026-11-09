# Person D — frontend & integration handover

Owner: Bill (Team 55) · Contract `HDBI-1.0.0` · Prepared release `150921447b27_c1.0.0_t0.1.2`

## Added D-owned code

- `app.py`: Streamlit entry point with correct `src/` path.
- `src/hdb_insights/app/services.py`: safe, lazy dispatch for CR's function module and Isaac's adapter class; error envelopes and connection lifetime; no automatic unsafe retry.
- `src/hdb_insights/app/options.py`: C05 MongoDB-to-shared dropdown normalization and options checks.
- `src/hdb_insights/app/comparison.py`: same-contract/release, read-only equivalent-query value comparison (no performance claims).
- `src/hdb_insights/app/ui.py`: Overview, Resale, Demographic, Mobility, CRUD Demo, Database Comparison.
- `tests/test_person_d.py`: 20 isolated unit/contract tests without DB servers.
- `SETUP_PERSON_D.md`: user manual, deployment, tests, known dependencies/decisions.
- `scripts/verify_prepared_release.py`: read-only SHA-256 and CSV row-count check.
- `scripts/check_adapter_contracts.py`: read-only static signature check across B/C's actual adapters (20 operations).

## Integration choices needing B/C/E confirmation

1. Adopt CR's proposed nested C05 option format, with D-only Mongo formatter; do not silently modify B/C core files.
2. Leave Mongo missing-mobility response unresolved (`DATA_NOT_READY`), as Isaac specified; avoid offering unpublished options.
3. Only expose initial ten cross-backend registered demo seeds for this exact release. Mongo's broader capability does not imply MariaDB can create from every record.
4. Final integration requires live active releases, Mongo collection validator and MariaDB app grants. D cannot validate from code-only ZIPs.

## Handover checklist

- [x] Implement all proposed UI explorers and safe demo CRUD calls.
- [x] Build same-filter/same-release comparison UI and error views.
- [x] Static compilation, isolated unit checks and prepared-release hashes.
- [x] Confirm original filenames and module source against Isaac's 2026-10-30 ZIP.
- [x] Align Mongo option display labels to the exact MariaDB loader labels.
- [x] Check signature compatibility (20/20 source signatures); runtime still untested.
- [ ] Confirm C05/nested response shape and missing-mobility behavior with B/C/E.
- [ ] Run two live backends; record release IDs and smoke-test outputs.
- [ ] Record E's independent result equivalence and controlled performance evidence.
- [ ] Add presentation screenshots from verified running app.
