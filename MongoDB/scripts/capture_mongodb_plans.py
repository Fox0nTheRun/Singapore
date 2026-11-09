"""Capture real executionStats for E; this is not a comparative benchmark."""
import argparse
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
import _mongo_bootstrap
from bson import json_util
from pymongo.errors import PyMongoError
from hdb_insights.db.mongo_contract import REGIONS, InputError, ServiceError, code, resale_filter, text
from hdb_insights.db.mongo_indexes import explain_find, explain_pipeline
from hdb_insights.db.mongo_queries import mobility_pipeline, resale_summary_pipeline
from hdb_insights.db.mongodb_adapter import MongoDBAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--town", required=True)
    parser.add_argument("--flat-type", required=True)
    parser.add_argument("--start-month", required=True)
    parser.add_argument("--end-month", required=True)
    parser.add_argument("--workplace", required=True)
    parser.add_argument("--region", default="ALL")
    parser.add_argument("--group-type", choices=("flat_type", "ethnicity"), default="flat_type")
    parser.add_argument("--group-code", default="4_ROOM")
    parser.add_argument("--survey-year", type=int, default=2018)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    filters = {"town_name": args.town, "flat_type_code": args.flat_type, "start_month": args.start_month, "end_month": args.end_month}
    try:
        predicate = resale_filter(filters)
        code(args.region, REGIONS, "region")
        text(args.workplace, "workplace")
    except InputError as exc:
        parser.error(str(exc))
    adapter = MongoDBAdapter()
    try:
        active = adapter._active()
        profile_result = adapter.demographic_profile(args.group_type, args.group_code, args.survey_year)
        if not profile_result["ok"] or profile_result["data"] is None:
            raise ValueError("Select an existing valid demographic profile")
        plans = {
            "Q-C-02": explain_find(adapter.db, "resale_transactions", predicate),
            "Q-C-03": explain_pipeline(adapter.db, "resale_transactions", resale_summary_pipeline(predicate)),
            "Q-C-05": explain_pipeline(adapter.db, "demographic_profiles", [{"$match": {"group_type": args.group_type, "group_code": args.group_code, "survey_year": args.survey_year}}, {"$project": {"_id": 0}}]),
            "Q-C-06": explain_pipeline(adapter.db, "mobility_profiles", mobility_pipeline(args.workplace, args.region, 2020)),
        }
        for plan in plans.values():
            if "serverInfo" in plan:
                plan["serverInfo"] = {key: value for key, value in plan["serverInfo"].items() if key in ("version", "gitVersion")}
            plan.pop("$clusterTime", None)
            plan.pop("operationTime", None)
        if adapter._active()["publication_id"] != active["publication_id"]:
            raise ValueError("Release changed while plans were collected")
        report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "contract_version": active["contract_version"],
            "data_release_id": active["data_release_id"], "pymongo_version": version("pymongo"),
            "mongodb_version": adapter.client.server_info()["version"], "parameters": vars(args),
            "indexes": {name: list(adapter.collection(name).list_indexes()) for name in ("resale_transactions", "demographic_profiles", "mobility_profiles")},
            "plans": plans, "interpretation": "Observed plans only; no cross-database speed claim. E must record hardware, caching, repetitions and result equivalence."}
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_util.dumps(report, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"status": "CAPTURED", "path": str(path), "query_ids": list(plans)}))
        return 0
    except (InputError, ServiceError, ValueError, OSError, PyMongoError) as exc:
        print(json.dumps({"status": "FAILED", "error_class": type(exc).__name__, "note": "No performance claim; check the active release, inputs and setup credentials"}))
        return 1
    finally:
        adapter.close()


if __name__ == "__main__":
    sys.exit(main())
