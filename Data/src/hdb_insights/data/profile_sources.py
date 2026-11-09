"""Read-only inventory and profiler for the eight HDBI source CSVs."""
from __future__ import annotations
import argparse, csv, hashlib, json
from collections import Counter
from pathlib import Path
from typing import Any
from .mappings import DATASETS
from .clean_mobility import MOBILITY_COLUMNS

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def profile_one(path: Path, dataset_id: str, expected_headers: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "dataset_id": dataset_id, "source_filename": path.name, "exists": path.is_file(),
        "source_sha256": None, "row_count": None, "headers": [], "empty_cells": 0,
        "duplicate_full_rows": None, "categorical_values": {}, "numeric_ranges": {},
        "header_match": None, "errors": [],
    }
    if not path.is_file():
        result["errors"].append("missing_file")
        return result
    result["source_sha256"] = sha256_file(path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, strict=True)
            headers = reader.fieldnames or []
            result["headers"] = headers
            result["header_match"] = (headers == expected_headers) if expected_headers else None
            if expected_headers and headers != expected_headers:
                result["errors"].append({"type": "header_mismatch", "expected": expected_headers, "observed": headers})
            row_count = 0
            duplicate_count = 0
            seen = set()
            cat = {}
            numeric = {}
            for row_number, row in enumerate(reader, start=1):
                if None in row:
                    result["errors"].append({"type": "extra_fields", "source_row_number": row_number})
                    continue
                row_count += 1
                values = tuple((row.get(h) or "") for h in headers)
                if values in seen:
                    duplicate_count += 1
                else:
                    seen.add(values)
                result["empty_cells"] += sum(1 for v in values if v.strip() == "")
                for h, value in zip(headers, values):
                    value = value.strip()
                    if not value:
                        continue
                    cat.setdefault(h, set()).add(value)
                    try:
                        number = float(value.replace(",", ""))
                        if number == number and abs(number) != float("inf"):
                            numeric.setdefault(h, []).append(number)
                    except (ValueError, TypeError):
                        pass
            result["row_count"] = row_count
            result["duplicate_full_rows"] = duplicate_count
            result["categorical_values"] = {k: sorted(v) for k, v in cat.items() if len(v) <= 100}
            result["numeric_ranges"] = {
                k: {"min": min(v), "max": max(v)} for k, v in numeric.items() if v
            }
    except (UnicodeDecodeError, csv.Error) as exc:
        result["errors"].append({"type": "csv_parse_error", "message": str(exc)})
    return result

def profile_sources(raw_dir: str | Path) -> dict[str, Any]:
    raw_dir = Path(raw_dir)
    results = []
    for dataset_id, spec in DATASETS.items():
        path = raw_dir / spec["filename"]
        expected_headers = ["Number", *MOBILITY_COLUMNS.keys()] if dataset_id == "D08" else spec["headers"]
        results.append(profile_one(path, dataset_id, expected_headers))
    return {
        "profile_version": "0.1.0",
        "raw_dir": str(raw_dir),
        "datasets": results,
        "summary": {
            "datasets_expected": len(DATASETS),
            "datasets_found": sum(1 for r in results if r["exists"]),
            "datasets_missing": [r["dataset_id"] for r in results if not r["exists"]],
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    args = parser.parse_args()
    report = profile_sources(args.raw_dir)
    out = Path(args.report_dir)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "source_profile.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written: {report_path}")
    return 0 if not report["summary"]["datasets_missing"] and all(not r["errors"] for r in report["datasets"]) else 1

if __name__ == "__main__":
    raise SystemExit(main())
