from pathlib import Path
import pandas as pd
from src.hdb_insights.data.clean_demographics import clean_demographic
from src.hdb_insights.data.clean_mobility import clean_mobility, MOBILITY_COLUMNS

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

def read_csv(name):
    return pd.read_csv(RAW / name, dtype=str, keep_default_na=False, encoding="utf-8-sig")

def test_demographic_transform_row_counts_and_mappings():
    cases = [
        ("D02", "Age of HDB Resident Population by Flat Type.csv", 63),
        ("D03", "Average and Median Age of HDB Resident Population by Flat Type.csv", 21),
        ("D04", "HDB Resident Population Aged 15 Years and Above by Flat Type.csv", 18),
        ("D05", "Age of HDB Resident Population by Ethnic Group.csv", 45),
        ("D06", "Average and Median Age of HDB Population by Ethnic Group.csv", 15),
        ("D07", "HDB Resident Population Aged 15 Years and Above by Ethnic Group.csv", 12),
    ]
    for did, filename, count in cases:
        frame, issues = clean_demographic(read_csv(filename), did, "a" * 64)
        assert len(frame) == count
        assert frame["source_row_number"].tolist() == list(range(1, count + 1))
        assert frame["dataset_id"].eq(did).all()
        assert not [issue for issue in issues if issue["severity"] == "error"]

def test_mobility_lossless_dash_and_special_categories():
    import hashlib
    from src.hdb_insights.data.mappings import DATASETS
    name = DATASETS["D08"]["filename"]
    df = read_csv(name)
    sha = hashlib.sha256((RAW / name).read_bytes()).hexdigest()
    out, issues = clean_mobility(df, sha)
    assert len(MOBILITY_COLUMNS) == 30
    assert len(out) == 1440
    assert (out["count_status"] == "unresolved_dash").sum() == 73
    assert all((v is None) or isinstance(v, int) for v in out["count"])
    assert out.loc[out["workplace_area"] == "Works from Home", "workplace_area_kind"].eq("special").all()
    assert out.duplicated(["survey_year", "workplace_area", "residence_region_code", "transport_mode_code"]).sum() == 0
    assert not [issue for issue in issues if issue["severity"] == "error"]
