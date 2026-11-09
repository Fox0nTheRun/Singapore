"""Read-only smoke checks by default; optional real-seed CRUD lifecycle."""
import argparse
import json
import sys
import _mongo_bootstrap
from pymongo.errors import PyMongoError
from hdb_insights.db.mongo_contract import EDITABLE_FIELDS
from hdb_insights.db.mongodb_adapter import MongoDBAdapter, proposed_options_formatter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-crud", action="store_true")
    parser.add_argument("--use-proposed-options-shape", action="store_true", help="Local preview only, pending D/B/E agreement")
    args = parser.parse_args()
    adapter = MongoDBAdapter(options_formatter=proposed_options_formatter if args.use_proposed_options_shape else None)
    results = {}
    try:
        results["search"] = adapter.search_resale({}, 1)
        if not results["search"]["ok"]:
            print(json.dumps(results, indent=2)); return 1
        results["summary"] = adapter.summarise_resale({})
        results["trend"] = adapter.resale_trend({})
        if args.use_proposed_options_shape:
            results["proposed_options"] = adapter.list_filter_options("resale")
        profile = adapter.collection("demographic_profiles").find_one({}, {"group_type": 1, "group_code": 1, "survey_year": 1})
        if profile:
            results["demographics"] = adapter.demographic_profile(profile["group_type"], profile["group_code"], profile["survey_year"])
        mobility = adapter.collection("mobility_profiles").find_one({}, {"workplace_area": 1, "survey_year": 1})
        if mobility:
            results["mobility"] = adapter.mobility_breakdown(mobility["workplace_area"], "ALL", mobility["survey_year"])
        if args.demo_crud:
            if not results["search"]["data"]["rows"]:
                print(json.dumps({"ok": False, "note": "A real resale seed is required for the CRUD demonstration"}))
                return 1
            seed = results["search"]["data"]["rows"][0]
            payload = {"seed_record_id": seed["record_id"], **{key: seed[key] for key in EDITABLE_FIELDS}}
            results["create_demo"] = adapter.create_demo_resale(payload)
            if results["create_demo"]["ok"]:
                identity = results["create_demo"]["data"]["demo_record_id"]
                results["read_demo"] = adapter.get_demo_resale(identity)
                results["update_demo"] = adapter.update_demo_resale(identity, {"resale_price": "555555.55"})
                results["invalid_update"] = adapter.update_demo_resale(identity, {"storey_lower": -1})
                results["delete_demo"] = adapter.delete_demo_resale(identity)
                results["read_deleted_demo"] = adapter.get_demo_resale(identity)
            results["analytics_after_demo"] = adapter.summarise_resale({})
        print(json.dumps(results, indent=2, allow_nan=False))
        expected_failures = {"invalid_update": "VALIDATION_ERROR", "read_deleted_demo": "NOT_FOUND"}
        success = True
        for key, value in results.items():
            if key in expected_failures:
                success = success and not value["ok"] and value["error"]["code"] == expected_failures[key]
            else:
                success = success and value["ok"]
        if args.demo_crud:
            success = success and results["summary"]["data"] == results["analytics_after_demo"]["data"]
        return 0 if success else 1
    except PyMongoError as exc:
        print(json.dumps({"ok": False, "error_class": type(exc).__name__, "note": "MongoDB smoke check failed; retain any demo identity already returned for reconciliation"}))
        return 1
    finally:
        adapter.close()


if __name__ == "__main__":
    sys.exit(main())
