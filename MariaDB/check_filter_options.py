import getpass
import json
import os

from src.hdb_insights.db.mariadb_repository import (
    list_filter_options,
    demographic_profile,
    mobility_breakdown,
)


def checked_options(domain):
    result = list_filter_options(domain)
    assert result["ok"], result
    assert result["error"] is None, result
    assert result["meta"]["backend"] == "mariadb", result
    assert result["meta"]["contract_version"] == "HDBI-1.0.0", result
    assert result["meta"]["data_release_id"] == (
        "150921447b27_c1.0.0_t0.1.2"
    ), result
    json.dumps(result, allow_nan=False)
    return result["data"]["options"]


def main():
    os.environ["MARIADB_PASSWORD"] = getpass.getpass(
        "hdb_app password (press Enter if blank): "
    )

    try:
        resale = checked_options("resale")

        towns = resale["town_names"]
        assert len(towns) == 26, towns
        assert towns == sorted(set(towns)), towns
        assert "ANG MO KIO" in towns

        types = resale["flat_types"]
        codes = [row["flat_type_code"] for row in types]
        assert codes == sorted(set(codes)), codes
        assert "4_ROOM" in codes
        assert "ALL" not in codes
        assert all(row["display_label"] for row in types)

        months = resale["registration_months"]
        assert months and months == sorted(set(months)), months
        assert "2020-01" in months and "2020-12" in months
        print("PASS: Resale options contain available, sorted choices.")

        demographic = checked_options("demographic")
        profiles = demographic["profiles"]

        keys = [
            (row["group_type"], row["group_code"], row["survey_year"])
            for row in profiles
        ]
        assert keys == sorted(set(keys)), keys
        assert ("flat_type", "4_ROOM", 2018) in keys
        assert ("ethnicity", "CHINESE", 2018) in keys
        assert ("flat_type", "ALL", 2018) in keys
        assert ("ethnicity", "ALL", 2018) in keys
        assert not any(
            row["group_code"] == "MULTI_GENERATION"
            for row in profiles
        )
        assert all(row["display_label"] for row in profiles)
        print("PASS: Demographic options preserve available combinations.")

        # Check every offered profile against the actual profile function.
        for row in profiles:
            result = demographic_profile(
                row["group_type"],
                row["group_code"],
                row["survey_year"],
            )
            assert result["ok"] and result["data"] is not None, (
                row, result
            )
        print("PASS: Every offered demographic profile can be retrieved.")

        mobility = checked_options("mobility")
        selections = mobility["selections"]

        keys = [
            (
                row["workplace_area"],
                row["residence_region_code"],
                row["survey_year"],
            )
            for row in selections
        ]
        assert keys == sorted(set(keys)), keys
        assert ("Total", "ALL", 2020) in keys
        print("PASS: Mobility options contain sorted available combinations.")

        # Also covers source special workplaces and individual regions.
        for row in selections:
            result = mobility_breakdown(
                row["workplace_area"],
                row["residence_region_code"],
                row["survey_year"],
            )
            assert result["ok"], (row, result)
        print("PASS: Every offered mobility breakdown can be retrieved.")

        for invalid in ("", "unknown", None, [], 123):
            result = list_filter_options(invalid)
            assert result["ok"] is False, result
            assert result["data"] is None, result
            assert result["error"]["code"] == "VALIDATION_ERROR", result
        print("PASS: Invalid domains are rejected.")

        print("\nAvailable choices:")
        print(f"Towns: {len(towns)}")
        print(f"Resale flat types: {len(types)}")
        print(f"Resale months: {len(months)}")
        print(f"Demographic profiles: {len(profiles)}")
        print(f"Mobility selections: {len(selections)}")

    finally:
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()