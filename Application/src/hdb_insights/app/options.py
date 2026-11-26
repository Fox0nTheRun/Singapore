"""C05 shared UI option shape for SQL and NoSQL (HDBI-1.0.0).

The backend returns the available categories. The formatter converts MongoDB's
DB-derived lists into the MariaDB-compatible nested wire shape; no CSV join or
backend aggregation is performed here.
"""
from __future__ import annotations

from typing import Any

# Exact display labels in load_mariadb.py, not inferred title-casing.
FLAT_LABELS = {
    "1_ROOM": "1-room", "2_ROOM": "2-room", "3_ROOM": "3-room",
    "4_ROOM": "4-room", "5_ROOM": "5-room", "EXECUTIVE": "Executive",
    "MULTI_GENERATION": "Multi-generation", "ALL": "All flat types",
}
ETHNIC_LABELS = {
    "CHINESE": "Chinese", "MALAY": "Malay", "INDIAN": "Indian",
    "OTHERS": "Others", "ALL": "All ethnic groups",
}


def _display_label(code: str, dimension: str) -> str:
    mapping = FLAT_LABELS if dimension == "flat_type" else ETHNIC_LABELS
    return mapping.get(code, str(code).replace("_", " ").title())


def mongo_options_formatter(domain: str, db_options: dict[str, Any]) -> dict[str, list]:
    """Convert internal MongoDB option keys to the shared C05 response format.

    list_filter_options() requires a formatter dependency supplied by
    backend_session().
    """
    if domain == "resale":
        return {
            "town_names": sorted(set(db_options["town_name"])),
            "flat_types": [
                {"flat_type_code": code, "display_label": _display_label(code, "flat_type")}
                for code in sorted(set(db_options["flat_type_code"]))
            ],
            "registration_months": sorted(set(db_options["registration_month"])),
        }

    if domain == "demographic":
        profiles = [
            {
                "group_type": row["group_type"],
                "group_code": row["group_code"],
                "display_label": _display_label(row["group_code"], row["group_type"]),
                "survey_year": int(row["survey_year"]),
            }
            for row in db_options["profiles"]
        ]
        return {"profiles": sorted(profiles, key=lambda r: (
            r["group_type"], r["group_code"], r["survey_year"]))}

    if domain == "mobility":
        # The MongoDB schema validates six residence regions * five observations
        # per workplace/year. Regions are DB-derived from the collection, and
        # the cross product is valid for the complete published data release.
        selections = {
            (str(row["workplace_area"]), str(region), int(row["survey_year"]))
            for row in db_options["workplaces"]
            for region in db_options["residence_region_code"]
        }
        return {"selections": [
            {"workplace_area": area, "residence_region_code": region, "survey_year": year}
            for area, region, year in sorted(selections)
        ]}
    raise ValueError("Unsupported domain")


def unpack_options(reply: dict, domain: str) -> dict:
    """Check the common nesting before rendering any dependent dropdowns."""
    if not reply.get("ok"):
        raise ValueError((reply.get("error") or {}).get("message", "Backend unavailable"))
    data = reply.get("data") or {}
    options = data.get("options")
    keys = {"resale": "town_names", "demographic": "profiles", "mobility": "selections"}
    if domain not in keys:
        raise ValueError("Unknown filter domain")
    if not isinstance(options, dict) or not isinstance(options.get(keys[domain]), list):
        raise ValueError(f"Missing or malformed {domain} filter options")
    return options
