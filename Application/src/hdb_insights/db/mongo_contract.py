"""C-owned constants and exact parsers for HDBI-1.0.0. No raw-data cleaning."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any

from bson.decimal128 import Decimal128
from bson.int64 import Int64

CONTRACT_VERSION = "HDBI-1.0.0"
SCHEMA_REVISION = "C-0.1.0"
AGE_CODES = ("BELOW_15", "AGE_15_64", "AGE_65_PLUS")
FLAT_CODES = ("1_ROOM", "2_ROOM", "3_ROOM", "4_ROOM", "5_ROOM", "EXECUTIVE")
RESALE_FLATS = (*FLAT_CODES, "MULTI_GENERATION")
ETHNIC_CODES = ("CHINESE", "MALAY", "INDIAN", "OTHERS")
REGIONS = ("ALL", "CENTRAL", "EAST", "NORTH", "NORTH_EAST", "WEST")
MODES = ("RAIL_BUS", "CAR_TAXI_PRIVATE_HIRE", "OTHER", "NO_TRANSPORT")
SPECIAL_AREAS = ("Other Planning Areas or Outside Singapore", "No Fixed Location for Work", "Works from Home")
DATASET_IDS = tuple(f"D{i:02}" for i in range(1, 9))
COLLECTIONS = ("source_datasets", "resale_transactions", "demographic_profiles", "mobility_profiles")
PROVENANCE = ("dataset_id", "source_file_sha256", "source_row_number")
RESALE_FIELDS = ("record_id", "registration_month", "town_name", "flat_type_code", "block", "street_name", "storey_lower", "storey_upper", "floor_area_sqm", "flat_model", "lease_commence_year", "remaining_lease_months", "resale_price")
EDITABLE_FIELDS = RESALE_FIELDS[1:]
HASH_RE = re.compile(r"[0-9a-f]{64}\Z")
MONTH_RE = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])\Z")
DECIMAL_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?\Z")
INT_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")


class InputError(ValueError):
    """Safe, non-secret contract validation failure."""


class ServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OutputSpec:
    filename: str
    business: tuple[str, ...]
    logical_key: tuple[str, ...]

    @property
    def headers(self) -> tuple[str, ...]:
        return self.business + PROVENANCE


SPECS = {
    "D01": OutputSpec("resale.csv", RESALE_FIELDS, ("record_id",)),
    "D02": OutputSpec("age_by_flat_type.csv", ("survey_year", "flat_type_code", "age_group_code", "percentage"), ("survey_year", "flat_type_code", "age_group_code")),
    "D03": OutputSpec("age_stats_by_flat_type.csv", ("survey_year", "flat_type_code", "average_age", "median_age"), ("survey_year", "flat_type_code")),
    "D04": OutputSpec("population_15_plus_by_flat_type.csv", ("survey_year", "flat_type_code", "population_15_plus"), ("survey_year", "flat_type_code")),
    "D05": OutputSpec("age_by_ethnicity.csv", ("survey_year", "ethnic_group_code", "age_group_code", "percentage"), ("survey_year", "ethnic_group_code", "age_group_code")),
    "D06": OutputSpec("age_stats_by_ethnicity.csv", ("survey_year", "ethnic_group_code", "average_age", "median_age"), ("survey_year", "ethnic_group_code")),
    "D07": OutputSpec("population_15_plus_by_ethnicity.csv", ("survey_year", "ethnic_group_code", "population_15_plus"), ("survey_year", "ethnic_group_code")),
    "D08": OutputSpec("mobility.csv", ("survey_year", "workplace_area", "workplace_area_kind", "residence_region_code", "transport_mode_code", "count", "count_status", "source_column"), ("survey_year", "workplace_area", "residence_region_code", "transport_mode_code")),
}

# Exact truncated source headers from packet section 3.3, not underscore guesses.
MOBILITY_COLUMNS = {
    "ALL": ("Total_Total", "Total_ModeofTransport_CombinationsofRail_MRT_LRT_orPublicBus", "Total_ModeofTransport_CarorTaxi_PrivateHireCarOnly", "Total_ModeofTransport_OtherModes", "Total_ModeofTransport_NoTransportRequired"),
    "CENTRAL": ("CentralRegion_Total", "CentralRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPubl", "CentralRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly", "CentralRegion_ModeofTransport_OtherModes", "CentralRegion_ModeofTransport_NoTransportRequired"),
    "EAST": ("EastRegion_Total", "EastRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPublicB", "EastRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly", "EastRegion_ModeofTransport_OtherModes", "EastRegion_ModeofTransport_NoTransportRequired"),
    "NORTH": ("NorthRegion_Total", "NorthRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPublic", "NorthRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly", "NorthRegion_ModeofTransport_OtherModes", "NorthRegion_ModeofTransport_NoTransportRequired"),
    "NORTH_EAST": ("North_EastRegion_Total", "North_EastRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orP", "North_EastRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly", "North_EastRegion_ModeofTransport_OtherModes", "North_EastRegion_ModeofTransport_NoTransportRequired"),
    "WEST": ("WestRegion_Total", "WestRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPublicB", "WestRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly", "WestRegion_ModeofTransport_OtherModes", "WestRegion_ModeofTransport_NoTransportRequired"),
}
COLUMN_MAP = {(region, mode): header for region, headers in MOBILITY_COLUMNS.items() for mode, header in zip(("ALL", *MODES), headers)}


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\x00" in value:
        raise InputError(f"{field}: expected nonempty, trimmed text")
    return value


def code(value: Any, allowed: tuple[str, ...], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise InputError(f"{field}: invalid code")
    return value


def integer(value: Any, field: str, minimum: int = 0, maximum: int = 2**31 - 1, *, csv: bool = False) -> int:
    if csv:
        if not isinstance(value, str) or not INT_RE.fullmatch(value):
            raise InputError(f"{field}: expected canonical integer text")
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise InputError(f"{field}: integer outside permitted range")
    return int(value)


def month(value: Any) -> str:
    if not isinstance(value, str) or not MONTH_RE.fullmatch(value) or value[:4] == "0000":
        raise InputError("Month must be YYYY-MM, with year 0001–9999")
    return value


def decimal128(value: Any, field: str, precision: int, *, positive: bool = False) -> Decimal128:
    if isinstance(value, Decimal128):
        number = value.to_decimal()
    elif isinstance(value, Decimal):
        number = value
    elif isinstance(value, str) and DECIMAL_RE.fullmatch(value):
        number = Decimal(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        number = Decimal(value)
    else:
        raise InputError(f"{field}: use a decimal string, Decimal or integer; no floats")
    if not number.is_finite() or number.as_tuple().exponent < -2:
        raise InputError(f"{field}: expected a finite number with at most two decimals")
    lower_bad = number <= 0 if positive else number < 0
    if lower_bad or number > Decimal(10) ** (precision - 2) - Decimal("0.01"):
        raise InputError(f"{field}: decimal outside permitted range")
    with localcontext() as ctx:
        ctx.prec = 40
        return Decimal128(number.quantize(Decimal("0.01")))


def decimal_text(value: Decimal128 | Decimal | None) -> str | None:
    if value is None:
        return None
    number = value.to_decimal() if isinstance(value, Decimal128) else value
    if not isinstance(number, Decimal) or not number.is_finite():
        raise InputError("Expected a finite database decimal")
    with localcontext() as ctx:
        ctx.prec = 40
        return format(number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def json_safe(value: Any) -> Any:
    if isinstance(value, (Decimal128, Decimal)):
        return decimal_text(value)
    if isinstance(value, Int64):
        return int(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_safe(v) for v in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise InputError("Unexpected driver value at public API boundary")


def resale_business(payload: dict, *, csv: bool = False, with_identity: bool = False) -> dict:
    fields = RESALE_FIELDS if with_identity else EDITABLE_FIELDS
    if not isinstance(payload, dict) or set(payload) != set(fields):
        raise InputError("Resale payload must contain exactly the required business fields")
    result = {k: text(payload[k], k) for k in ("town_name", "block", "street_name", "flat_model")}
    for k in ("town_name", "street_name"):
        if result[k] != result[k].upper():
            raise InputError(f"{k}: expected canonical uppercase text")
    result["registration_month"] = month(payload["registration_month"])
    result["flat_type_code"] = code(payload["flat_type_code"], RESALE_FLATS, "flat_type_code")
    for k in ("storey_lower", "storey_upper", "lease_commence_year", "remaining_lease_months"):
        result[k] = integer(payload[k], k, 1 if k == "lease_commence_year" else 0, 9999 if k == "lease_commence_year" else 2**31 - 1, csv=csv)
    if result["storey_lower"] > result["storey_upper"]:
        raise InputError("storey_lower must not exceed storey_upper")
    result["floor_area_sqm"] = decimal128(payload["floor_area_sqm"], "floor_area_sqm", 8, positive=True)
    result["resale_price"] = decimal128(payload["resale_price"], "resale_price", 14, positive=True)
    if with_identity:
        result["record_id"] = text(payload["record_id"], "record_id")
    return result


def resale_filter(filters: Any) -> dict:
    if not isinstance(filters, dict) or set(filters) - {"town_name", "flat_type_code", "start_month", "end_month"}:
        raise InputError("Unknown resale filter or invalid filter object")
    result: dict = {}
    if filters.get("town_name") is not None:
        result["town_name"] = text(filters["town_name"], "town_name")
    if filters.get("flat_type_code") is not None:
        result["flat_type_code"] = code(filters["flat_type_code"], RESALE_FLATS, "flat_type_code")
    start = month(filters["start_month"]) if filters.get("start_month") is not None else None
    end = month(filters["end_month"]) if filters.get("end_month") is not None else None
    if start and end and start > end:
        raise InputError("start_month must not exceed end_month")
    if start or end:
        result["registration_month"] = {**({"$gte": start} if start else {}), **({"$lte": end} if end else {})}
    return result
