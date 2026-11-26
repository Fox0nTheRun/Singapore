"""Restore the prior release from a checked publication journal; app stays offline."""
import argparse
import json
import sys
import _mongo_bootstrap
from pymongo.errors import PyMongoError
from hdb_insights.db.mongo_connection import connect, database
from hdb_insights.db.mongo_contract import InputError
from hdb_insights.db.mongo_loader import rollback_publication


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--maintenance-confirmed", action="store_true", required=True)
    args = parser.parse_args()
    try:
        with connect() as client:
            state = rollback_publication(database(client), args.journal, maintenance_confirmed=args.maintenance_confirmed)
        print(json.dumps({"status": state["phase"], "note": "Prior content verified; inspect readiness before resuming the app"}, indent=2))
        return 0
    except (InputError, OSError, PyMongoError, ValueError, KeyError) as exc:
        print("Recovery incomplete: "+type(exc).__name__+". Keep the app offline and retain the journal.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
