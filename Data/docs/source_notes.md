# Source notes and baseline controls

Contract: HDBI-1.0.0. Source filenames and expected row counts are from Person A packet A-1.0.0, issued 23 October 2026. These are baseline controls, not evidence that this implementation has processed the files.

| ID | Exact filename | Baseline rows | Output |
|---|---|---:|---|
| D01 | `Resale flat prices based on registration date from Jan-2017 onwards.csv` | 240,468 | `resale.csv` |
| D02 | `Age of HDB Resident Population by Flat Type.csv` | 63 | `age_by_flat_type.csv` |
| D03 | `Average and Median Age of HDB Resident Population by Flat Type.csv` | 21 | `age_stats_by_flat_type.csv` |
| D04 | `HDB Resident Population Aged 15 Years and Above by Flat Type.csv` | 18 | `population_15_plus_by_flat_type.csv` |
| D05 | `Age of HDB Resident Population by Ethnic Group.csv` | 45 | `age_by_ethnicity.csv` |
| D06 | `Average and Median Age of HDB Population by Ethnic Group.csv` | 15 | `age_stats_by_ethnicity.csv` |
| D07 | `HDB Resident Population Aged 15 Years and Above by Ethnic Group.csv` | 12 | `population_15_plus_by_ethnicity.csv` |
| D08 | `EmployedResidentsAged15YearsandOverbyPlanningAreaofWorkplaceUsu.csv` | 48 | `mobility.csv` |

Baseline caveats:
- D01 contains 318 duplicate full-row occurrences beyond first occurrences. Retain them; no source transaction ID exists.
- D02–D07 percentages may total 100.1 due to published precision; preserve values and warn.
- Population totals by flat type and ethnicity differ by 1,000 in each survey year; preserve both and document.
- D08 is 48 × 31; reshape to 1,440 observations. There are 73 `-` tokens; until a source-specific legend confirms meaning, encode as null with `count_status=unresolved_dash`.
- D08 `Number` labels workplace planning-area categories; regions are regions of residence. Metadata year is 2020.
- Never join mobility workplace areas to resale towns or invent ethnicity-by-town/flat-type relationships.
- Exact D08 30-header mapping is specified in the supplied Person A instruction file, section 3.3, and must be copied into a later `clean_mobility.py`.
