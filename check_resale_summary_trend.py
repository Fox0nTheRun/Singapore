import json
import os
from getpass import getpass

from src.hdb_insights.db.mariadb_repository import (
    summarise_resale,
    resale_trend,
)


def successful_data(result):
    assert result["ok"], result["error"]
    json.dumps(result)
    return result["data"]


def main():
    os.environ["MARIADB_PASSWORD"] = getpass("hdb_app password: ")

    try:
        filters = {
            "town_name": "ANG MO KIO",
            "flat_type_code": "4_ROOM",
            "start_month": "2020-01",
            "end_month": "2020-12",
        }

        summary = successful_data(summarise_resale(filters))
        assert summary == {
            "transaction_count": 301,
            "average_price": "449672.57",
            "average_price_per_sqm": "4853.37",
        }, summary
        print("PASS: summary matches previously verified SQL results.")

        rows = successful_data(resale_trend(filters))["rows"]
        assert len(rows) == 12
        assert [row["registration_month"] for row in rows] == [
            f"2020-{month:02d}" for month in range(1, 13)
        ]
        assert [row["transaction_count"] for row in rows] == [
            29, 27, 20, 3, 5, 30, 25, 35, 39, 27, 33, 28
        ]
        assert sum(row["transaction_count"] for row in rows) == 301
        assert rows[0]["average_price"] == "441540.97"
        assert rows[0]["average_price_per_sqm"] == "4739.60"
        print("PASS: monthly ordering, counts and January averages.")

        empty_filters = {
            **filters,
            "start_month": "1900-01",
            "end_month": "1900-12",
        }

        empty_summary = successful_data(
            summarise_resale(empty_filters)
        )
        assert empty_summary == {
            "transaction_count": 0,
            "average_price": None,
            "average_price_per_sqm": None,
        }
        assert successful_data(resale_trend(empty_filters)) == {
            "rows": []
        }
        print("PASS: empty results preserve null averages and no months.")

        for function in (summarise_resale, resale_trend):
            result = function({
                "start_month": "2020-12",
                "end_month": "2020-01",
            })
            assert not result["ok"]
            assert result["error"]["code"] == "VALIDATION_ERROR"

        print("PASS: both functions reject reversed date ranges.")
        print("\nSummary:")
        print(json.dumps(summary, indent=2))

    finally:
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()