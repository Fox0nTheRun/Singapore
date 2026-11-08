import getpass
import json
import os
from pathlib import Path

from src.hdb_insights.db.mariadb_connection import get_connection
from src.hdb_insights.db.mariadb_repository import (
    create_demo_resale,
    get_demo_resale,
)


STATE_FILE = Path(__file__).resolve().with_name("demo_test_record.json")


def main():
    os.environ["MARIADB_PASSWORD"] = getpass.getpass(
        "hdb_app password (press Enter if blank): "
    )

    try:
        # Avoid creating another record accidentally on a repeat run.
        if STATE_FILE.exists():
            saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            previous = get_demo_resale(saved["demo_record_id"])
            if previous["ok"]:
                print("A saved demo test record already exists:")
                print(saved["demo_record_id"])
                print("Keep it for the Update step. No new record created.")
                return
            assert previous["error"]["code"] == "NOT_FOUND", previous

        connection = get_connection()
        try:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute("""
                    SELECT
                        r.record_id AS seed_record_id,
                        r.registration_month,
                        t.town_name,
                        r.flat_type_code,
                        r.block,
                        r.street_name,
                        r.storey_lower,
                        r.storey_upper,
                        r.floor_area_sqm,
                        r.flat_model,
                        r.lease_commence_year,
                        r.remaining_lease_months,
                        r.resale_price
                    FROM hdb_insights_demo.demo_seed AS s
                    JOIN hdb_insights.resale_transaction AS r
                        ON r.record_id = s.seed_record_id
                    JOIN hdb_insights.town AS t
                        ON t.town_id = r.town_id
                    JOIN hdb_insights.application_metadata AS m
                        ON m.metadata_id = 1
                        AND m.data_release_id = s.base_data_release_id
                    ORDER BY r.record_id
                    LIMIT 1
                """)
                payload = cursor.fetchone()
            finally:
                cursor.close()
        finally:
            connection.close()

        assert payload is not None, "No registered seed available."

        invalid = dict(payload, resale_price="-1.00")
        rejected = create_demo_resale(invalid)
        assert rejected["ok"] is False, rejected
        assert rejected["error"]["code"] == "VALIDATION_ERROR", rejected
        print("PASS: Negative price is rejected.")

        invalid = dict(payload, demo_record_id="demo:client-supplied")
        rejected = create_demo_resale(invalid)
        assert rejected["ok"] is False, rejected
        assert rejected["error"]["code"] == "VALIDATION_ERROR", rejected
        print("PASS: Client-supplied identity is rejected.")

        created = create_demo_resale(payload)
        assert created["ok"], created
        record = created["data"]

        # Retain the ID for the following Update and Delete steps.
        STATE_FILE.write_text(
            json.dumps(record, indent=2, allow_nan=False),
            encoding="utf-8",
        )

        assert record["demo_record_id"].startswith("demo:"), record
        assert record["record_kind"] == "demo", record
        assert record["seed_record_id"] == payload["seed_record_id"], record
        assert record["base_data_release_id"] == (
            "150921447b27_c1.0.0_t0.1.2"
        ), record

        for field, value in payload.items():
            if field in {"floor_area_sqm", "resale_price"}:
                assert record[field] == format(value, ".2f"), record
            else:
                assert record[field] == value, (field, record)

        print("PASS: Demo creation returns the expected values and lineage.")

        # This opens a separate connection, proving the commit is visible.
        retrieved = get_demo_resale(record["demo_record_id"])
        assert retrieved["ok"], retrieved
        assert retrieved["data"] == record, retrieved
        assert retrieved["meta"]["dataset_kind"] == "demo", retrieved
        assert retrieved["meta"]["base_data_release_id"] == (
            record["base_data_release_id"]
        ), retrieved
        print("PASS: A separate connection reads the committed record.")

        print("\nSaved demo ID:", record["demo_record_id"])
        print("State file:", STATE_FILE)

    finally:
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()


def _modify_demo_resale(operation, demo_record_id, changes=None):
    meta = {
        "backend": "mariadb",
        "contract_version": CONTRACT_VERSION,
        "data_release_id": None,
        "dataset_kind": "demo",
        "base_data_release_id": None,
    }
    connection = None

    try:
        _validate_demo_record_id(demo_record_id)

        if operation not in {"update", "delete"}:
            raise RuntimeError("Unknown demo operation.")

        if operation == "update":
            if not isinstance(changes, dict) or not changes:
                raise ValidationError(
                    "changes must be a non-empty dictionary."
                )
            if set(changes) - DEMO_BUSINESS_FIELDS:
                raise ValidationError(
                    "Only resale business fields can be updated; "
                    "identity and lineage cannot be changed."
                )

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("START TRANSACTION")

        cursor.execute("""
            SELECT contract_version, data_release_id
            FROM hdb_insights.application_metadata
            WHERE metadata_id = 1
            LOCK IN SHARE MODE
        """)
        metadata = cursor.fetchone()

        if (
            metadata is None
            or metadata["contract_version"] != CONTRACT_VERSION
            or not metadata["data_release_id"]
        ):
            raise DataNotReadyError()

        active_release = metadata["data_release_id"]
        meta["data_release_id"] = active_release

        cursor.execute(
            """
            SELECT base_data_release_id
            FROM hdb_insights_demo.demo_resale_transaction
            WHERE demo_record_id = ?
            FOR UPDATE
            """,
            (demo_record_id,),
        )
        locked = cursor.fetchone()

        if locked is None:
            return _response(
                meta,
                code="NOT_FOUND",
                message="The requested demo record does not exist.",
            )

        meta["base_data_release_id"] = locked["base_data_release_id"]

        if locked["base_data_release_id"] != active_release:
            return _response(
                meta,
                code="DATA_NOT_READY",
                message="This demo record belongs to a different release.",
            )

        if operation == "delete":
            cursor.execute(
                """
                DELETE FROM hdb_insights_demo.demo_resale_transaction
                WHERE demo_record_id = ?
                """,
                (demo_record_id,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Expected exactly one deleted record.")

            result = _response(meta, data={"deleted_count": 1})

        else:
            existing = _read_demo_row(cursor, demo_record_id)
            if existing is None:
                raise RuntimeError("Locked demo record could not be read.")

            # Validate the complete resulting record, including rules
            # involving two fields such as lower/upper storeys.
            combined = {
                field: existing[field] for field in DEMO_BUSINESS_FIELDS
            }
            combined.update(changes)
            values = _validate_demo_business(combined)

            cursor.execute(
                """
                SELECT town_id
                FROM hdb_insights_demo.town
                WHERE town_name = ?
                """,
                (values["town_name"],),
            )
            town = cursor.fetchone()
            if town is None:
                raise ValidationError("Unknown demo town_name.")

            cursor.execute(
                """
                SELECT flat_type_code
                FROM hdb_insights_demo.flat_type
                WHERE flat_type_code = ? AND flat_type_code <> 'ALL'
                """,
                (values["flat_type_code"],),
            )
            if cursor.fetchone() is None:
                raise ValidationError("Unknown demo flat_type_code.")

            cursor.execute(
                """
                UPDATE hdb_insights_demo.demo_resale_transaction
                SET registration_month = ?,
                    town_id = ?,
                    flat_type_code = ?,
                    block = ?,
                    street_name = ?,
                    storey_lower = ?,
                    storey_upper = ?,
                    floor_area_sqm = ?,
                    flat_model = ?,
                    lease_commence_year = ?,
                    remaining_lease_months = ?,
                    resale_price = ?
                WHERE demo_record_id = ?
                """,
                (
                    values["registration_month"],
                    town["town_id"],
                    values["flat_type_code"],
                    values["block"],
                    values["street_name"],
                    values["storey_lower"],
                    values["storey_upper"],
                    values["floor_area_sqm"],
                    values["flat_model"],
                    values["lease_commence_year"],
                    values["remaining_lease_months"],
                    values["resale_price"],
                    demo_record_id,
                ),
            )

            # Updating a field to its existing value is still successful.
            updated = _read_demo_row(cursor, demo_record_id)
            if updated is None:
                raise RuntimeError("Updated record could not be read.")

            result = _response(meta, data=_serialise(updated))

        cursor.close()
        connection.commit()
        return result

    except ValidationError as error:
        return _response(
            meta, code="VALIDATION_ERROR", message=str(error)
        )

    except DataNotReadyError:
        return _response(
            meta,
            code="DATA_NOT_READY",
            message="A compatible analytical release has not been loaded.",
        )

    except mariadb.Error as error:
        LOGGER.error("Demo modification failed; errno=%s", error.errno)

        if error.errno in {1062, 1205, 1213}:
            code = "CONFLICT"
        elif error.errno in {1040, 1042, 1045, 2002, 2003, 2006, 2013}:
            code = "DB_UNAVAILABLE"
        else:
            code = "INTERNAL_ERROR"

        return _response(
            meta,
            code=code,
            message="The demo modification could not be confirmed.",
        )

    except Exception as error:
        LOGGER.error("Demo modification failed: %s", type(error).__name__)
        return _response(
            meta,
            code="INTERNAL_ERROR",
            message="The demo modification could not be completed.",
        )

    finally:
        if connection is not None:
            connection.close()


def update_demo_resale(demo_record_id, changes):
    return _modify_demo_resale("update", demo_record_id, changes)


def delete_demo_resale(demo_record_id):
    return _modify_demo_resale("delete", demo_record_id)


