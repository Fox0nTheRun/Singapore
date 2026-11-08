import getpass
import json
import os

from src.hdb_insights.db.mariadb_repository import demographic_profile


RELEASE = "150921447b27_c1.0.0_t0.1.2"


def checked_profile(group_type, group_code, year):
    result = demographic_profile(group_type, group_code, year)

    assert result["ok"], result
    assert result["error"] is None, result
    assert result["meta"]["backend"] == "mariadb", result
    assert result["meta"]["contract_version"] == "HDBI-1.0.0", result
    assert result["meta"]["data_release_id"] == RELEASE, result
    json.dumps(result, allow_nan=False)

    return result


def main():
    os.environ["MARIADB_PASSWORD"] = getpass.getpass(
        "hdb_app password (press Enter if blank): "
    )

    try:
        result = checked_profile("flat_type", "4_ROOM", 2018)
        profile = result["data"]

        assert profile["average_age"] == "39.80", profile
        assert profile["median_age"] == "40.00", profile
        assert profile["population_15_plus"] == 1084000, profile
        assert profile["population_status"] == "reported", profile
        assert profile["age_distribution"] == [
            {"age_group_code": "BELOW_15", "percentage": "15.20"},
            {"age_group_code": "AGE_15_64", "percentage": "70.70"},
            {"age_group_code": "AGE_65_PLUS", "percentage": "14.10"},
        ], profile
        print("PASS: 2018 4_ROOM matches the verified SQL results.")

        source_rows = profile["source_rows"]
        assert len(source_rows) == 5, source_rows
        assert source_rows == sorted(
            source_rows,
            key=lambda row: (
                row["dataset_id"],
                row["source_row_number"],
                row["source_file_sha256"],
            ),
        ), source_rows
        assert all(
            len(row["source_file_sha256"]) == 64
            and row["source_row_number"] >= 1
            for row in source_rows
        ), source_rows
        print("PASS: Five contributing source rows are returned in order.")

        ethnicity = checked_profile("ethnicity", "CHINESE", 2018)["data"]
        assert ethnicity is not None
        assert ethnicity["group_code"] == "CHINESE"
        assert ethnicity["population_status"] == "reported"
        assert len(ethnicity["age_distribution"]) == 3
        assert len(ethnicity["source_rows"]) == 5
        print("PASS: Ethnicity profile structure and lineage.")

        for dimension in ("flat_type", "ethnicity"):
            aggregate = checked_profile(dimension, "ALL", 2018)["data"]
            assert aggregate is not None
            assert aggregate["population_15_plus"] is None, aggregate
            assert aggregate["population_status"] == "not_provided", aggregate
            assert len(aggregate["source_rows"]) == 4, aggregate
        print("PASS: ALL profiles preserve missing population as null.")

        for dimension, code, year in [
            ("flat_type", "MULTI_GENERATION", 2018),
            ("flat_type", "4_ROOM", 1900),
        ]:
            missing = checked_profile(dimension, code, year)
            assert missing["data"] is None, missing
            assert missing["meta"].get("note"), missing
        print("PASS: Unavailable profiles return success with null data.")

        invalid_inputs = [
            ("town", "ANG MO KIO", 2018),
            ("flat_type", "INVALID_CODE", 2018),
            ("flat_type", "", 2018),
            ("flat_type", "4_ROOM", "2018"),
            ("flat_type", "4_ROOM", True),
        ]

        for arguments in invalid_inputs:
            rejected = demographic_profile(*arguments)
            assert rejected["ok"] is False, rejected
            assert rejected["data"] is None, rejected
            assert rejected["error"]["code"] == "VALIDATION_ERROR", rejected
        print("PASS: Invalid dimensions, codes and year types are rejected.")

        print("\nVerified flat-type profile:")
        print(json.dumps(result, indent=2))

    finally:
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()