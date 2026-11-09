"""D01 resale transformation; preserves every source row and exact decimal values."""
from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation
import pandas as pd

INPUT_HEADERS = ["month", "town", "flat_type", "block", "street_name", "storey_range",
                 "floor_area_sqm", "flat_model", "lease_commence_date", "remaining_lease", "resale_price"]
OUTPUT_HEADERS = ["record_id", "registration_month", "town_name", "flat_type_code", "block", "street_name",
                  "storey_lower", "storey_upper", "floor_area_sqm", "flat_model", "lease_commence_year",
                  "remaining_lease_months", "resale_price", "dataset_id", "source_file_sha256", "source_row_number"]
FLAT_TYPE = {"1 ROOM":"1_ROOM","2 ROOM":"2_ROOM","3 ROOM":"3_ROOM","4 ROOM":"4_ROOM",
             "5 ROOM":"5_ROOM","EXECUTIVE":"EXECUTIVE","MULTI-GENERATION":"MULTI_GENERATION"}

def parse_decimal(value: str, field: str, scale: int) -> Decimal:
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field}: invalid decimal {value!r}")
    if not number.is_finite():
        raise ValueError(f"{field}: non-finite decimal")
    exponent = number.as_tuple().exponent
    if exponent < -scale:
        raise ValueError(f"{field}: precision exceeds {scale} decimal places: {value!r}")
    return number

def parse_storey(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s+TO\s+(\d+)\s*", value, flags=re.I)
    if not match:
        raise ValueError(f"invalid storey_range {value!r}")
    lower, upper = map(int, match.groups())
    if lower > upper:
        raise ValueError(f"storey range is reversed: {value!r}")
    return lower, upper

def parse_remaining_lease(value: str) -> int:
    text = value.strip().lower()
    match = re.fullmatch(
        r"(?:(\d+)\s+years?)?(?:\s*(\d+)\s+months?)?", text
    )
    if not match or not any(match.groups()):
        raise ValueError(f"invalid remaining_lease {value!r}")
    years = int(match.group(1) or 0)
    months = int(match.group(2) or 0)
    if not 0 <= months <= 11:
        raise ValueError(f"remaining lease months must be 0..11: {value!r}")
    return years * 12 + months

def clean_resale(raw_frame: pd.DataFrame, source_sha256: str) -> tuple[pd.DataFrame, list[dict]]:
    if list(raw_frame.columns) != INPUT_HEADERS:
        raise ValueError(f"D01 headers mismatch. Expected {INPUT_HEADERS}; got {list(raw_frame.columns)}")
    rows, issues = [], []
    for source_row_number, source in enumerate(raw_frame.to_dict(orient="records"), start=1):
        try:
            month = str(source["month"]).strip()
            if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
                raise ValueError(f"invalid registration month {month!r}")
            flat_raw = str(source["flat_type"]).strip().upper()
            if flat_raw not in FLAT_TYPE:
                raise ValueError(f"unknown flat_type {flat_raw!r}")
            lower, upper = parse_storey(str(source["storey_range"]))
            area = parse_decimal(str(source["floor_area_sqm"]), "floor_area_sqm", 2)
            price = parse_decimal(str(source["resale_price"]), "resale_price", 2)
            lease_year = int(str(source["lease_commence_date"]).strip())
            lease_months = parse_remaining_lease(str(source["remaining_lease"]))
            if area <= 0 or price <= 0:
                raise ValueError("floor area and resale price must be positive")
            if lease_year < 1900 or lease_year > int(month[:4]):
                issues.append({"severity":"warning","dataset_id":"D01","source_row_number":source_row_number,
                               "rule_id":"D01_LEASE_YEAR_RANGE","message":"Lease commencement year is unusual; review source semantics."})
            rows.append({
                "record_id": f"D01:{source_sha256}:{source_row_number:09d}",
                "registration_month": month, "town_name": str(source["town"]).strip().upper(),
                "flat_type_code": FLAT_TYPE[flat_raw], "block": str(source["block"]).strip(),
                "street_name": str(source["street_name"]).strip().upper(),
                "storey_lower": lower, "storey_upper": upper,
                "floor_area_sqm": format(area, ".2f"), "flat_model": str(source["flat_model"]).strip(),
                "lease_commence_year": lease_year, "remaining_lease_months": lease_months,
                "resale_price": format(price, ".2f"), "dataset_id": "D01",
                "source_file_sha256": source_sha256, "source_row_number": source_row_number,
            })
        except Exception as exc:
            issues.append({"severity":"error","dataset_id":"D01","source_row_number":source_row_number,
                           "message":str(exc),"action":"quarantined"})
    frame = pd.DataFrame(rows, columns=OUTPUT_HEADERS)
    if not frame.empty and frame["record_id"].duplicated().any():
        raise ValueError("record_id uniqueness check failed")
    return frame, issues
