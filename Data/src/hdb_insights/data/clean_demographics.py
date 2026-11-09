"""Loss-aware cleaning for demographic inputs D02-D07."""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import pandas as pd
FLAT_TYPE = {"1-ROOM":"1_ROOM", "1 ROOM":"1_ROOM", "2-ROOM":"2_ROOM", "2 ROOM":"2_ROOM", "3-ROOM":"3_ROOM", "3 ROOM":"3_ROOM", "4-ROOM":"4_ROOM", "4 ROOM":"4_ROOM", "5-ROOM":"5_ROOM", "5 ROOM":"5_ROOM", "EXECUTIVE":"EXECUTIVE", "MULTI-GENERATION":"MULTI_GENERATION", "ALL":"ALL"}
ETHNICITY = {"CHINESE":"CHINESE", "MALAY":"MALAY", "INDIAN":"INDIAN", "OTHERS":"OTHERS", "ALL":"ALL"}
AGE_GROUP = {"BELOW 15":"BELOW_15", "15-64":"AGE_15_64", "65 & ABOVE":"AGE_65_PLUS"}
DEMOGRAPHIC_SCHEMAS = {
    "D02": ("age_by_flat_type.csv", ["survey_year","flat_type_code","age_group_code","percentage"], ["shs_year","flat_type","age_group","percentage"], "flat", "age"),
    "D03": ("age_stats_by_flat_type.csv", ["survey_year","flat_type_code","average_age","median_age"], ["shs_year","flat_type","average_age","median_age"], "flat", "stats"),
    "D04": ("population_15_plus_by_flat_type.csv", ["survey_year","flat_type_code","population_15_plus"], ["shs_year","flat_type","number"], "flat", "population"),
    "D05": ("age_by_ethnicity.csv", ["survey_year","ethnic_group_code","age_group_code","percentage"], ["shs_year","ethnic_group","age_group","percentage"], "ethnicity", "age"),
    "D06": ("age_stats_by_ethnicity.csv", ["survey_year","ethnic_group_code","average_age","median_age"], ["shs_year","ethnic_group","average_age","median_age"], "ethnicity", "stats"),
    "D07": ("population_15_plus_by_ethnicity.csv", ["survey_year","ethnic_group_code","population_15_plus"], ["shs_year","ethnic_group","number"], "ethnicity", "population"),
}
PROVENANCE = ["dataset_id", "source_file_sha256", "source_row_number"]
def _decimal(value: str, field: str, scale: int) -> Decimal:
    try: n = Decimal(value.strip())
    except (InvalidOperation, AttributeError): raise ValueError(f"{field}: invalid decimal {value!r}")
    if not n.is_finite(): raise ValueError(f"{field}: non-finite decimal")
    if n.as_tuple().exponent < -scale: raise ValueError(f"{field}: precision exceeds {scale} decimal places: {value!r}")
    return n
def clean_demographic(raw_frame: pd.DataFrame, dataset_id: str, source_sha256: str):
    if dataset_id not in DEMOGRAPHIC_SCHEMAS: raise ValueError(f"unsupported demographic dataset {dataset_id}")
    _, business_cols, source_cols, dimension, kind = DEMOGRAPHIC_SCHEMAS[dataset_id]
    if list(raw_frame.columns) != source_cols: raise ValueError(f"{dataset_id} headers mismatch. Expected {source_cols}; got {list(raw_frame.columns)}")
    rows, issues = [], []
    category_map = FLAT_TYPE if dimension == "flat" else ETHNICITY
    category_field = "flat_type_code" if dimension == "flat" else "ethnic_group_code"
    for row_num, src in enumerate(raw_frame.to_dict(orient="records"), start=1):
        try:
            year_text = str(src["shs_year"]).strip()
            if not year_text.isdigit(): raise ValueError(f"invalid survey year {year_text!r}")
            year = int(year_text)
            category_raw = str(src["flat_type" if dimension == "flat" else "ethnic_group"]).strip().upper()
            if category_raw not in category_map: raise ValueError(f"unknown {dimension} label {category_raw!r}")
            row = {"survey_year": year, category_field: category_map[category_raw]}
            if kind == "age":
                age_raw = str(src["age_group"]).strip().upper()
                if age_raw not in AGE_GROUP: raise ValueError(f"unknown age group {age_raw!r}")
                pct = _decimal(str(src["percentage"]), "percentage", 2)
                if not Decimal("0") <= pct <= Decimal("100"): raise ValueError(f"percentage out of range: {pct}")
                row.update({"age_group_code": AGE_GROUP[age_raw], "percentage": format(pct, ".2f")})
            elif kind == "stats":
                avg = _decimal(str(src["average_age"]), "average_age", 2)
                med = _decimal(str(src["median_age"]), "median_age", 2)
                if avg < 0 or med < 0: raise ValueError("age values must be nonnegative")
                row.update({"average_age": format(avg, ".2f"), "median_age": format(med, ".2f")})
            else:
                value = str(src["number"]).strip()
                if not value.isdigit(): raise ValueError(f"population count must be a nonnegative integer: {value!r}")
                row["population_15_plus"] = int(value)
            row.update({"dataset_id": dataset_id, "source_file_sha256": source_sha256, "source_row_number": row_num})
            rows.append(row)
        except Exception as exc:
            issues.append({"severity":"error", "dataset_id":dataset_id, "source_row_number":row_num, "message":str(exc), "action":"quarantined"})
    frame = pd.DataFrame(rows, columns=business_cols + PROVENANCE)
    key_cols = {
        "D02":["survey_year","flat_type_code","age_group_code"], "D03":["survey_year","flat_type_code"], "D04":["survey_year","flat_type_code"],
        "D05":["survey_year","ethnic_group_code","age_group_code"], "D06":["survey_year","ethnic_group_code"], "D07":["survey_year","ethnic_group_code"]}[dataset_id]
    if not frame.empty and frame.duplicated(key_cols).any():
        for _, r in frame[frame.duplicated(key_cols, keep=False)].iterrows():
            issues.append({"severity":"error","dataset_id":dataset_id,"source_row_number":int(r["source_row_number"]),"rule_id":"DUPLICATE_KEY","message":f"duplicate business key {tuple(r[k] for k in key_cols)}","action":"blocked"})
    if kind == "age" and not frame.empty:
        expected_age = {"BELOW_15", "AGE_15_64", "AGE_65_PLUS"}
        for key, group in frame.groupby(["survey_year", category_field], dropna=False):
            observed = set(group["age_group_code"])
            if observed != expected_age:
                issues.append({"severity":"error","dataset_id":dataset_id,"rule_id":"AGE_GROUP_COVERAGE","message":f"{key}: expected {sorted(expected_age)}, observed {sorted(observed)}","action":"blocked"})
            total = sum((Decimal(str(x)) for x in group["percentage"]), Decimal("0"))
            if total != Decimal("100.00"):
                severity = "warning" if abs(total-Decimal("100")) <= Decimal("0.2") else "error"
                issues.append({"severity":severity,"dataset_id":dataset_id,"rule_id":"AGE_PERCENTAGE_SUM","message":f"{key}: percentages sum to {total}; source values retained","action":"retained" if severity=="warning" else "blocked"})
    return frame, issues
