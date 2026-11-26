# Data preparation decisions and caveats

- Contract used: `HDBI-1.0.0`; transform version: `0.1.2`.
- All eight source-file hashes match the reference fingerprints. Original CSV files were not modified by the pipeline.
- D01: all 240,468 source rows retained, including 318 duplicate occurrences beyond the first. No address/month/price or full-row deduplication applied. `record_id` is derived from source hash and parsed row number.
- D02-D07: each source row retained. Percentage inputs remain on the source's 0–100 scale; values are formatted to two decimals, not renormalised. Four category/year groups sum to 100.1 and are warnings within the specified 0.2-point tolerance.
- Demographic population counts describe residents aged 15+, while age distribution percentages include children; their denominators are not interchangeable. Flat-type and ethnicity totals that differ by 1,000 are not reconciled.
- D08: explicit mapping of all 30 truncated headers; 48 × 30 = 1,440 output observations. Pivot-back check reproduced all 1,440 source tokens. All 73 `-` cells were stored as null with `unresolved_dash` status; their statistical meaning remains unverified.
- D08 subtotal/mode reconciliation found 93 complete comparisons with a difference between the published subtotal and the sum of four reported modes. The differences are recorded as warnings; published counts remain unchanged.
- D08 `workplace_area` identifies workplace category; `residence_region_code` identifies region of residence. No join to resale towns or invented commute-level relationship is made.
- Local data preparation tests and CSV release checks passed. MariaDB/MongoDB loads, database equivalence, Streamlit flows and integration tests remain unverified by the data preparation checks.
