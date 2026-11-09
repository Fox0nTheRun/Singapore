import getpass
import json
import os
from decimal import Decimal
from pathlib import Path

from src.hdb_insights.db.mariadb_connection import get_connection
from src.hdb_insights.db.mariadb_repository import (
    DEMO_BUSINESS_FIELDS,
    create_demo_resale,
    get_demo_resale,
    update_demo_resale,
    delete_demo_resale,
)


STATE_FILE = Path(__file__).resolve().with_name("demo_test_record.json")


def successful(result):
    assert result["ok"], result
    assert result["error"] is None, result
    assert result["meta"]["dataset_kind"] == "demo", result
    assert result["meta"]["contract_version"] == "HDBI-1.0.0", result
    json.dumps(result, allow_nan=False)
    return result["data"]


def rejected(result, code):
    assert result["ok"] is False, result
    assert result["data"] is None, result
    assert result["error"]["code"] == code, result


def analytical_snapshot(seed_id):
    connection = get_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT *
                FROM hdb_insights.resale_transaction
                WHERE record_id = ?
                """,
                (seed_id,),
            )
            source = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*) AS n FROM hdb_insights.resale_transaction"
            )
            count = cursor.fetchone()["n"]
            return source, count
        finally:
            cursor.close()
    finally:
        connection.close()


def main():
    os.environ["MARIADB_PASSWORD"] = getpass.getpass(
        "hdb_app password (press Enter if blank): "
    )
    test_id = None

    try:
        assert STATE_FILE.exists(), (
            "demo_test_record.json is missing; keep the file from Create."
        )
        saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))

        payload = {
            field: saved[field] for field in DEMO_BUSINESS_FIELDS
        }
        payload["seed_record_id"] = saved["seed_record_id"]

        before = analytical_snapshot(payload["seed_record_id"])
        assert before[0] is not None
        assert before[1] == 240468, before[1]

        # CREATE and READ using separate connections.
        created = successful(create_demo_resale(payload))
        test_id = created["demo_record_id"]
        assert successful(get_demo_resale(test_id)) == created
        print("PASS: Create and committed read-back.")

        identity = {
            field: created[field]
            for field in (
                "demo_record_id",
                "record_kind",
                "seed_record_id",
                "base_data_release_id",
            )
        }

        # UPDATE to a valid price different from the current price.
        new_price = (
            "250000.00"
            if Decimal(created["resale_price"]) != Decimal("250000")
            else "250001.00"
        )
        updated = successful(
            update_demo_resale(test_id, {"resale_price": new_price})
        )
        expected = dict(created, resale_price=new_price)
        assert updated == expected, updated
        assert successful(get_demo_resale(test_id)) == expected
        assert all(updated[key] == value for key, value in identity.items())
        print("PASS: Update persists and preserves other fields and lineage.")

        unchanged = successful(
            update_demo_resale(test_id, {"resale_price": new_price})
        )
        assert unchanged == expected
        print("PASS: Updating to the same value succeeds.")

        # Each rejected edit must leave the stored record unchanged.
        invalid_changes = [
            {},
            {"seed_record_id": "changed"},
            {"base_data_release_id": "changed"},
            {"demo_record_id": "changed"},
            {"record_kind": "analytical"},
            {"resale_price": "-1.00"},
            {"floor_area_sqm": "44.001"},
            {"storey_lower": updated["storey_upper"] + 1},
            {"town_name": "NOT_A_REAL_TOWN"},
            {"flat_type_code": "ALL"},
        ]

        for changes in invalid_changes:
            rejected(
                update_demo_resale(test_id, changes),
                "VALIDATION_ERROR",
            )
            assert successful(get_demo_resale(test_id)) == expected
        print("PASS: Invalid edits are rejected without changing the record.")

        # DELETE and confirm absence from another connection.
        deleted = successful(delete_demo_resale(test_id))
        assert deleted == {"deleted_count": 1}, deleted
        rejected(get_demo_resale(test_id), "NOT_FOUND")
        rejected(delete_demo_resale(test_id), "NOT_FOUND")
        rejected(
            update_demo_resale(test_id, {"resale_price": new_price}),
            "NOT_FOUND",
        )
        test_id = None
        print("PASS: Delete persists; subsequent operations return NOT_FOUND.")

        # Remove only the earlier record created by check_demo_create.py.
        cleanup = delete_demo_resale(saved["demo_record_id"])
        if cleanup["ok"]:
            assert cleanup["data"] == {"deleted_count": 1}, cleanup
        else:
            rejected(cleanup, "NOT_FOUND")

        assert analytical_snapshot(payload["seed_record_id"]) == before
        print("PASS: Analytical seed and resale row count are unchanged.")

        print("\nCRUD suite passed. Both identified test records are removed.")
        print("Keep demo_test_record.json as the repeatable test input.")

    finally:
        # If a check fails, attempt cleanup of this run's own record.
        try:
            if test_id is not None:
                cleanup = delete_demo_resale(test_id)
                if not cleanup["ok"]:
                    print("Cleanup needs attention:", test_id, cleanup)
        finally:
            os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()