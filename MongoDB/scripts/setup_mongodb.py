"""Default: inspect. Flags create missing collections or deliberately migrate."""
import argparse
import sys
import _mongo_bootstrap
from bson import json_util
from pymongo.errors import PyMongoError
from hdb_insights.db.mongo_connection import connect, database
from hdb_insights.db.mongo_contract import COLLECTIONS, InputError
from hdb_insights.db.mongo_schema import ensure_collection
from hdb_insights.db.mongo_indexes import create_indexes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-missing", action="store_true")
    parser.add_argument("--create-demo", action="store_true")
    parser.add_argument("--apply-schema-update", action="store_true", help="Explicitly change inspected existing validators; existing data must already pass")
    args = parser.parse_args()
    try:
        with connect() as client:
            client.admin.command("ping")
            db = database(client)
            report = {"analytical": {}, "demo": {}}
            for name in (*COLLECTIONS, "application_metadata"):
                if args.create_missing or args.apply_schema_update:
                    ensure_collection(db, name, name, apply_schema_update=args.apply_schema_update)
                    create_indexes(db[name], name)
                report["analytical"][name] = {"options": db[name].options(), "indexes": list(db[name].list_indexes()) if name in db.list_collection_names() else []}
            if args.create_demo:
                demo_db = database(client, "hdb_insights_demo")
                name = "demo_resale_transactions"
                ensure_collection(demo_db, name, name, apply_schema_update=args.apply_schema_update)
                report["demo"] = {"options": demo_db[name].options(), "indexes": list(demo_db[name].list_indexes())}
        print(json_util.dumps(report, indent=2))
        return 0
    except InputError as exc:
        print(str(exc), file=sys.stderr)
    except PyMongoError as exc:
        print("MongoDB setup failed: "+type(exc).__name__+"; no reset was performed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
