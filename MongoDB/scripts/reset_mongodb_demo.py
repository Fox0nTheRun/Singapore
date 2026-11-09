"""Explicitly remove only demo records for a named base release; never analytics."""
import argparse
import json
import sys
import _mongo_bootstrap
from pymongo.errors import PyMongoError
from hdb_insights.db.mongo_connection import connect, database
from hdb_insights.db.mongo_contract import InputError
from hdb_insights.db.mongo_schema import demo_validator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-release", required=True)
    parser.add_argument("--reset-demo", required=True, action="store_true")
    args = parser.parse_args()
    try:
        with connect() as client:
            collection = database(client, "hdb_insights_demo").demo_resale_transactions
            if collection.options().get("validator") != demo_validator():
                raise InputError("Demo validator not recognised; no records were deleted")
            result = collection.delete_many({"record_kind": "demo", "base_data_release_id": args.base_release})
            if not result.acknowledged:
                raise InputError("Reset not acknowledged")
        print(json.dumps({"dataset_kind": "demo", "deleted_count": result.deleted_count}))
        return 0
    except (InputError, PyMongoError) as exc:
        print(str(exc) if isinstance(exc, InputError) else type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
