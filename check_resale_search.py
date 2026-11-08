import json
import os
from getpass import getpass

from src.hdb_insights.db.mariadb_repository import search_resale


def main():
    os.environ["MARIADB_PASSWORD"] = getpass("hdb_app password: ")

    try:
        filters = {
            "town_name": "ANG MO KIO",
            "flat_type_code": "4_ROOM",
            "start_month": "2020-01",
            "end_month": "2020-12",
        }

        result = search_resale(filters, limit=20, offset=0)

        if not result["ok"]:
            raise RuntimeError(result["error"])

        data = result["data"]

        assert data["total_count"] == 301, data["total_count"]
        assert len(data["rows"]) == 20, len(data["rows"])
        assert result["meta"]["data_release_id"] == (
            "150921447b27_c1.0.0_t0.1.2"
        )

        for row in data["rows"]:
            assert row["town_name"] == "ANG MO KIO"
            assert row["flat_type_code"] == "4_ROOM"
            assert "2020-01" <= row["registration_month"] <= "2020-12"
            assert isinstance(row["resale_price"], str)
            assert isinstance(row["floor_area_sqm"], str)

        keys = [
            (row["registration_month"], row["record_id"])
            for row in data["rows"]
        ]
        assert keys == sorted(keys)

        # Verify that the complete response can be serialised.
        json.dumps(result)

        invalid = search_resale({"flat_type_code": "ALL"})
        assert not invalid["ok"]
        assert invalid["error"]["code"] == "VALIDATION_ERROR"

        empty_page = search_resale(filters, limit=20, offset=301)
        assert empty_page["ok"]
        assert empty_page["data"]["rows"] == []
        assert empty_page["data"]["total_count"] == 301

        print("PASS: matching count = 301.")
        print("PASS: first page contains 20 correctly filtered rows.")
        print("PASS: ordering and JSON serialisation.")
        print("PASS: ALL rejected as a resale flat type.")
        print("PASS: pagination beyond the last record.")
        print("\nFirst returned record:")
        print(json.dumps(data["rows"][0], indent=2))

    finally:
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()