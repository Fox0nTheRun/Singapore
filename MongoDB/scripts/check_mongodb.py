"""Non-destructive diagnostics: no URI, host list or credentials are printed."""
import json
import platform
import sys
from importlib.metadata import version
import _mongo_bootstrap
from pymongo.errors import PyMongoError
from hdb_insights.db.mongo_connection import connect, database


def main():
    report = {"python_version": platform.python_version(), "pymongo_version": version("pymongo"), "server_status": "NOT_REACHED"}
    try:
        with connect() as client:
            client.admin.command("ping")
            hello = client.admin.command("hello")
            report.update(server_status="PING_OK", mongodb_version=client.server_info()["version"],
                topology="router" if hello.get("msg") == "isdbgrid" else "replica_set" if hello.get("setName") else "standalone")
            db = database(client)
            expected = {"source_datasets", "resale_transactions", "demographic_profiles", "mobility_profiles", "application_metadata"}
            report["project_collections_present"] = sorted(set(db.list_collection_names()) & expected)
            report["active_release"] = db.application_metadata.find_one({"_id": "active"}, {"_id": 0, "data_release_id": 1, "contract_version": 1})
    except PyMongoError as exc:
        report.update(error_class=type(exc).__name__, next_step="Check that MongoDB is running and MONGODB_URI is correct; do not share the URI")
    except ValueError:
        report.update(error_class="InvalidDatabaseName", next_step="Check MONGODB_DATABASE")
    print(json.dumps(report, indent=2))
    return 0 if report["server_status"] == "PING_OK" and "error_class" not in report else 1


if __name__ == "__main__":
    sys.exit(main())
