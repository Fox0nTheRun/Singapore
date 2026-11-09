# Revision summary — Person D after original Isaac handover (8 Nov 2026)

## Why the change was small but useful

The previously assembled `mongodb_adapter.py` was identical to Isaac's original source. Seven other MongoDB core modules had no substantive source differences (only trailing blank lines). We therefore preserved the application architecture rather than replacing it unnecessarily.

## Changes owned by Person D

1. **Dropdown interoperability:** `src/hdb_insights/app/options.py` now uses the exact category labels from Chang Rong's MariaDB seed maps (rather than generic title-casing). The output structure still matches MariaDB's provisional C05 `data.options` interface.
2. **Response safety:** `src/hdb_insights/app/services.py` verifies the response envelope and backend identity, and confirms the expected contract and nonempty published release on successful results. Signature mismatches produce explicit safe errors. MongoDB connections still close after each call; there is no automatic retry of demo writes.
3. **Correctness comparison:** `src/hdb_insights/app/comparison.py` now keeps integer/count types exact instead of treating fractional counts as equal after rounding. Decimal measurements are compared at their reported two-decimal precision. `None` is never converted into zero; narrative notes alone are ignored for mobility comparison.
4. **Mobility terminology:** Streamlit labels workplace special categories accurately, separately from residence regions.
5. **Testing:** `tests/test_person_d.py` expanded from 11 to 20 passing isolated tests. `scripts/check_adapter_contracts.py` statically checks 20 original B/C callable signatures.
6. **Original MongoDB packaging:** integrated ZIP now ships the original C files and filenames, rather than guessed script aliases, plus original tests, fixtures and historical evidence. `docs/ISAAC_HANDOVER_CONFIRMATION.md` explains what is and is not verified.
7. **Documentation:** setup instructions reference actual MongoDB scripts and explain remaining live testing and team contract decisions.

## Testing status

- D isolated unit/contract checks: **20 passed** in the current environment.
- Static B/C interface signature checks: **PASS (20/20)**.
- Prepared Xavier release checks: **PASS (eight file hashes and row counts)**.
- Python syntax compile: **PASS**.
- Not executed: live MariaDB, MongoDB or Streamlit browser tests and independent SQL/NoSQL equivalence. Driver packages/database servers are unavailable in this environment.

## What Bill should merge into GitHub

Use the `Bill_Person_D_Revised_Isaac_Confirmed.zip` archive. Copy its files into the shared repository while leaving original B/C backend modules untouched. The full integrated ZIP is an integration workspace, not a replacement for the shared team's live database or credentials.

**Before presenting:** run both databases against the same published data release, validate all four explorer pages, execute a demo CRUD cycle in the isolated demo database, and ask Xi Fa to sign off on equivalent-query results. The team's recorded C05 filter shape and missing-mobility policy still need agreement from B/C/E.
