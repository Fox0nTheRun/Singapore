"""Preflight first. Default stages only; publication needs offline acknowledgement."""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import _mongo_bootstrap
from pymongo.errors import PyMongoError
from hdb_insights.db.mongo_connection import connect, database
from hdb_insights.db.mongo_contract import InputError
from hdb_insights.db.mongo_loader import load_release
from hdb_insights.db.mongo_prepared import PreparedRelease


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--maintenance-confirmed", action="store_true", help="Application has been stopped and all readers/writers drained")
    parser.add_argument("--journal", help="New local journal filename; keep it for recovery")
    parser.add_argument("--report", help="Write sanitized load report to this path")
    args = parser.parse_args()
    if args.dry_run and args.publish:
        parser.error("--dry-run and --publish are mutually exclusive")
    if args.publish and not args.maintenance_confirmed:
        parser.error("--publish requires --maintenance-confirmed after stopping/draining the application")
    report = {"status": "FAILED", "database_load": "NOT_RUN", "timestamp_utc": datetime.now(timezone.utc).isoformat()}
    try:
        release = PreparedRelease(args.release_dir)
        report.update(release.preflight(), status="PREFLIGHT_OK")
        if not args.dry_run:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            journal = args.journal or str(Path("docs/evidence/C/load") / (stamp+"_recovery.json"))
            with connect() as client:
                client.admin.command("ping")
                outcome = load_release(release, database(client), journal,
                    publish=args.publish, maintenance_confirmed=args.maintenance_confirmed)
            report.update(outcome, database_load=outcome["status"])
    except (InputError, OSError, ValueError, UnicodeError, csv.Error) as exc:
        # Contract messages and local file error *class*, never DB credentials.
        report.update(status="FAILED", error=str(exc) if isinstance(exc, InputError) else type(exc).__name__)
    except PyMongoError as exc:
        report.update(status="FAILED", error=type(exc).__name__, next_step="Inspect/recover any cutover journal before restarting the app; staging failures do not publish metadata")
    result = json.dumps(report, indent=2)
    print(result)
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result+"\n", encoding="utf-8")
    return 1 if report["status"] == "FAILED" else 0


if __name__ == "__main__":
    sys.exit(main())
