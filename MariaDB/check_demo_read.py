import getpass
import json
import os
from uuid import uuid4

from src.hdb_insights.db.mariadb_repository import get_demo_resale


def main():
    os.environ["MARIADB_PASSWORD"] = getpass.getpass(
        "hdb_app password (press Enter if blank): "
    )

    try:
        # A newly generated ID has not been inserted.
        missing_id = f"demo:{uuid4()}"
        result = get_demo_resale(missing_id)

        assert result["ok"] is False, result
        assert result["data"] is None, result
        assert result["error"]["code"] == "NOT_FOUND", result
        print("PASS: A nonexistent demo record returns NOT_FOUND.")

        assert result["meta"]["backend"] == "mariadb", result
        assert result["meta"]["dataset_kind"] == "demo", result
        assert result["meta"]["contract_version"] == "HDBI-1.0.0", result
        assert result["meta"]["data_release_id"] == (
            "150921447b27_c1.0.0_t0.1.2"
        ), result

        # No record means there is no record-specific base release.
        assert result["meta"]["base_data_release_id"] is None, result
        json.dumps(result, allow_nan=False)
        print("PASS: Demo metadata and response are JSON-compatible.")

        for invalid_id in (
            None,
            "",
            123,
            [],
            "not-a-demo-id",
            "demo:123",
            "D01:analytical-record",
        ):
            rejected = get_demo_resale(invalid_id)
            assert rejected["ok"] is False, rejected
            assert rejected["data"] is None, rejected
            assert rejected["error"]["code"] == "VALIDATION_ERROR", rejected

        print("PASS: Invalid demo IDs are rejected.")
        print("\nExisting-record read will be checked after Create.")

    finally:
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()