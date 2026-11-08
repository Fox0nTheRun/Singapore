import getpass
import json
import os

from src.hdb_insights.db.mariadb_connection import get_connection
from src.hdb_insights.db.mariadb_repository import mobility_breakdown


def checked_breakdown(workplace, region, year=2020):
    result = mobility_breakdown(workplace, region, year)

    assert result["ok"], result
    assert result["error"] is None, result
    assert result["meta"]["backend"] == "mariadb", result
    assert result["meta"]["contract_version"] == "HDBI-1.0.0", result
    assert result["meta"]["data_release_id"] == (
        "150921447b27_c1.0.0_t0.1.2"
    ), result

    json.dumps(result, allow_nan=False)
    return result


def main():
    os.environ["MARIADB_PASSWORD"] = getpass.getpass(
        "hdb_app password (press Enter if blank): "
    )

    try:
        result = checked_breakdown("Total", "ALL")
        data = result["data"]

        expected = [
            ("RAIL_BUS", 1257434, "57.75"),
            ("CAR_TAXI_PRIVATE_HIRE", 526477, "24.18"),
            ("OTHER", 180639, "8.30"),
            ("NO_TRANSPORT", 212907, "9.78"),
        ]

        actual = [
            (row["transport_mode_code"], row["count"], row["share_pct"])
            for row in data["rows"]
        ]

        assert actual == expected, actual
        assert all(
            row["count_status"] == "reported"
            for row in data["rows"]
        )
        assert data["published_total"] == 2177456, data
        print("PASS: National counts, mode order and shares match SQL.")

        # The source's mode counts exceed its published total by one.
        # Preserve this difference rather than changing the data.
        assert sum(row["count"] for row in data["rows"]) == 2177457
        assert data["note"], data
        print("PASS: Published rounding difference is preserved.")

        # Locate a real unresolved mode without inventing a test location.
        connection = get_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT workplace_area, residence_region_code,
                           survey_year, transport_mode_code
                    FROM mobility_observation
                    WHERE count_status = 'unresolved_dash'
                      AND transport_mode_code <> 'ALL'
                    ORDER BY survey_year, workplace_area,
                             residence_region_code, transport_mode_code
                    LIMIT 1
                """)
                example = cursor.fetchone()
            finally:
                cursor.close()
        finally:
            connection.close()

        assert example is not None, "No unresolved mode found."

        unresolved = checked_breakdown(
            example["workplace_area"],
            example["residence_region_code"],
            example["survey_year"],
        )

        mode = next(
            row for row in unresolved["data"]["rows"]
            if row["transport_mode_code"] == example["transport_mode_code"]
        )

        assert mode["count"] is None, mode
        assert mode["count_status"] == "unresolved_dash", mode
        assert mode["share_pct"] is None, mode
        print("PASS: A real unresolved count and its share remain null.")

        invalid_inputs = [
            ("", "ALL", 2020),
            ("NOT_A_REAL_WORKPLACE", "ALL", 2020),
            ("Total", "INVALID_REGION", 2020),
            ("Total", "ALL", "2020"),
            ("Total", "ALL", True),
        ]

        for arguments in invalid_inputs:
            rejected = mobility_breakdown(*arguments)
            assert rejected["ok"] is False, rejected
            assert rejected["data"] is None, rejected
            assert rejected["error"]["code"] == "VALIDATION_ERROR", rejected
        print("PASS: Invalid workplace, region and year inputs are rejected.")

        print("\nVerified national breakdown:")
        print(json.dumps(result, indent=2))

    finally:
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()