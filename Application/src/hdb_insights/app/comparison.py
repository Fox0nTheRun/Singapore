"""Person D's descriptive equivalent-query comparison (no speed claims)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .services import call, CONTRACT_VERSION


QUERIES = {"search_resale", "summarise_resale", "resale_trend", "demographic_profile", "mobility_breakdown"}


INTEGER_FIELDS = frozenset({
    "total_count", "limit", "offset", "transaction_count", "storey_lower",
    "storey_upper", "lease_commence_year", "remaining_lease_months",
    "survey_year", "population_15_plus", "source_row_number", "count", "published_total",
})
DECIMAL_FIELDS = frozenset({
    "average_price", "average_price_per_sqm", "floor_area_sqm", "resale_price",
    "average_age", "median_age", "percentage", "share_pct",
})


def canonical(value: Any, field: str | None = None) -> Any:
    """Normalise only numeric database *fields*, not arbitrary numeric-like text.

    Block identifiers such as '001' must not silently compare equal to '1'.
    Null stays null and never becomes zero.
    """
    if isinstance(value, dict):
        return {k: canonical(v, k) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [canonical(v, field) for v in value]
    if value is None or isinstance(value, bool):
        return value
    if field in INTEGER_FIELDS:
        try:
            numeric = Decimal(str(value))
            # Do not round fractional counts into valid-looking integers.
            return int(numeric) if numeric.is_finite() and numeric == numeric.to_integral_value() else value
        except (InvalidOperation, ValueError, OverflowError):
            return value
    if field in DECIMAL_FIELDS:
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return value
    return value


def projection(op: str, data: Any) -> Any:
    if data is None:
        return None
    if op == "mobility_breakdown":
        return {"published_total": data.get("published_total"), "rows": data.get("rows")}
    if op == "demographic_profile":
        return {k: data.get(k) for k in (
            "group_type", "group_code", "survey_year", "average_age", "median_age",
            "population_15_plus", "population_status", "age_distribution", "source_rows")}
    return data


def differences(left: Any, right: Any, path: str = "data", limit: int = 15) -> list[str]:
    mismatches: list[str] = []

    def visit(a: Any, b: Any, p: str):
        if len(mismatches) >= limit:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    mismatches.append(f"{p}.{key}: field missing from one backend")
                else:
                    visit(a[key], b[key], f"{p}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                mismatches.append(f"{p}: lengths {len(a)} and {len(b)} differ")
            for index, (x, y) in enumerate(zip(a, b)):
                visit(x, y, f"{p}[{index}]")
        elif a != b:
            mismatches.append(f"{p}: values differ")

    visit(left, right, path)
    return mismatches


def compare(op: str, *args: Any, **kwargs: Any) -> dict:
    if op not in QUERIES:
        raise ValueError("Not an equivalent analytical query")
    maria = call("mariadb", op, *args, **kwargs)
    mongo = call("mongodb", op, *args, **kwargs)
    result = {"mariadb": maria, "mongodb": mongo, "status": "not_comparable", "differences": []}
    if not maria["ok"] or not mongo["ok"]:
        result["differences"] = ["At least one query failed; inspect the two response envelopes."]
        return result
    m_meta = maria.get("meta") or {}
    n_meta = mongo.get("meta") or {}
    if m_meta.get("contract_version") != CONTRACT_VERSION or n_meta.get("contract_version") != CONTRACT_VERSION:
        result["differences"] = ["The backend contracts are not the expected version."]
        return result
    if not m_meta.get("data_release_id") or m_meta.get("data_release_id") != n_meta.get("data_release_id"):
        result["differences"] = ["The databases are not on the same published data release."]
        return result
    issues = differences(canonical(projection(op, maria["data"])), canonical(projection(op, mongo["data"])))
    result["differences"] = issues
    result["status"] = "match" if not issues else "mismatch"
    return result
