from decimal import Decimal
import pandas as pd
import pytest
from src.hdb_insights.data.clean_resale import parse_remaining_lease, parse_storey, parse_decimal, clean_resale, INPUT_HEADERS

def test_remaining_lease_variants():
    assert parse_remaining_lease("61 years 04 months") == 736
    assert parse_remaining_lease("1 year 01 month") == 13
    assert parse_remaining_lease("60 years") == 720

def test_storey():
    assert parse_storey("10 TO 12") == (10, 12)
    with pytest.raises(ValueError):
        parse_storey("12 TO 10")

def test_decimal_precision():
    assert parse_decimal("44.00", "area", 2) == Decimal("44.00")
    with pytest.raises(ValueError):
        parse_decimal("1.234", "area", 2)

def test_duplicate_source_rows_keep_distinct_ids():
    row = ["2017-01","ANG MO KIO","2 ROOM","406","ANG MO KIO AVE 10","10 TO 12",
           "44","Model A","1979","61 years 04 months","232000"]
    raw = pd.DataFrame([row, row], columns=INPUT_HEADERS)
    cleaned, issues = clean_resale(raw, "a"*64)
    assert len(cleaned) == 2
    assert cleaned["record_id"].nunique() == 2
    assert cleaned["source_row_number"].tolist() == [1, 2]
    assert not [i for i in issues if i["severity"] == "error"]
