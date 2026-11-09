# Data dictionary — HDBI-1.0.0

This is the initial contract summary. Final verified dictionary must be updated from actual profiling runs.

## D01 — `resale.csv`
One row per published source transaction. Ordered columns:
`record_id,registration_month,town_name,flat_type_code,block,street_name,storey_lower,storey_upper,floor_area_sqm,flat_model,lease_commence_year,remaining_lease_months,resale_price,dataset_id,source_file_sha256,source_row_number`.

- `registration_month`: source registration month `YYYY-MM`; not completion date.
- `town_name`, `street_name`: trimmed uppercase text.
- `flat_type_code`: `1_ROOM`, `2_ROOM`, `3_ROOM`, `4_ROOM`, `5_ROOM`, `EXECUTIVE`, `MULTI_GENERATION`.
- `block`: text; retain letters/leading zeroes.
- `storey_lower`, `storey_upper`: integers parsed from `N TO N`.
- `floor_area_sqm`: DECIMAL(8,2); `resale_price`: DECIMAL(14,2), parsed without silent rounding.
- `lease_commence_year`: integer from source year.
- `remaining_lease_months`: total months parsed from source text.
- Provenance: dataset ID, source file SHA-256 and one-based parsed data-record number.

## D02–D07 — demographic outputs
Keep the six datasets separate. Survey years are 2008, 2013, 2018. Age groups: `BELOW_15`, `AGE_15_64`, `AGE_65_PLUS`; percentages 0–100. Means and medians are source-provided years of age. Population figures count residents aged 15+. The age distribution includes children, so its denominator must not be treated as population 15+. Do not fabricate `ALL` population rows where source tables omit them.

## D08 — `mobility.csv`
One row per source value cell: 48 workplace-category rows × 30 source value columns = 1,440 rows. Columns:
`survey_year,workplace_area,workplace_area_kind,residence_region_code,transport_mode_code,count,count_status,source_column,dataset_id,source_file_sha256,source_row_number`.
`count` is nullable integer; `count_status` is `reported` or `unresolved_dash`. The latter retains the fact that the source token was `-`; do not convert it to zero without a verified source legend and central amendment. Residence region is not workplace region.
