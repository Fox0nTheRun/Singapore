# HDB Insights — Person A (Data Preparation)

Person A implementation for contract `HDBI-1.0.0`. The project contains a read-only profiler, transformations for all eight supplied CSV datasets, a deterministic release pipeline, data validation, tests and independent prepared-data controls.

## Verified local release

- Release ID: `150921447b27_c1.0.0_t0.1.2`
- Source rows: D01 240,468; D02 63; D03 21; D04 18; D05 45; D06 15; D07 12; D08 48 rows × 30 values.
- Output rows: resale 240,468; demographic outputs 63, 21, 18, 45, 15 and 12; mobility 1,440.
- All eight raw hashes match the supplied briefing fingerprints. The 318 repeated D01 row occurrences were retained. D08's 73 dash tokens remain null with `unresolved_dash` status.
- Latest full run completed with zero blocking errors and 98 documented warnings (source subtotal/percentage discrepancies and unresolved D08 dash semantics). Unit tests passed locally.
- This status covers only the Person A local data-preparation outputs. MariaDB/MongoDB loaders and full application integration are not verified.

## Setup and rerun

Use the team-compatible Python environment. Install the dependencies with:

```bash
python -m pip install -r requirements.txt
```

From the project root, run:

```bash
python -m src.hdb_insights.data.profile_sources --raw-dir data/raw --report-dir docs/evidence/A/profile
python -m src.hdb_insights.data.pipeline --raw-dir data/raw --output-root data/processed --report-dir docs/evidence/A/release --transform-version 0.1.2
python -m src.hdb_insights.data.control_totals --release-dir data/processed/150921447b27_c1.0.0_t0.1.2 --output docs/evidence/A/controls/control_totals.json
python -m pytest -q tests/data
```

Raw CSVs in `data/raw/` are copies of the input bytes. Do not edit or overwrite them. Pipeline outputs are published under `data/processed/<data_release_id>/` with a `manifest.json` and `validation_issues.json`. Do not manually change outputs inside a release folder.

## Important source caveats

- D01 has no unique source transaction identifier. Generated record IDs identify source rows and are reproducible for identical input bytes/order.
- D02–D07 contain source percentages that can total 100.1 after display rounding; retain values, do not renormalise.
- Population counts are residents aged 15+; age-distribution percentages include people below 15.
- D08's `-` meaning remains unresolved and must not be treated as zero. Published mode components may differ from subtotals; source totals are retained and discrepancies are documented.
