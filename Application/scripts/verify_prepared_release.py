"""Read-only verification of Xavier's processed release, no DB access."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", default="data/processed/150921447b27_c1.0.0_t0.1.2")
    args = parser.parse_args()
    root = Path(args.release_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    report = []
    for info in manifest["outputs"]:
        file = root / info["filename"]
        actual_hash = hashlib.sha256(file.read_bytes()).hexdigest()
        with file.open("r", newline="", encoding="utf-8-sig") as stream:
            actual_rows = sum(1 for _ in csv.reader(stream)) - 1
        report.append({"file": file.name, "rows": actual_rows,
            "hash_matches": actual_hash == info["output_sha256"],
            "row_count_matches": actual_rows == info["row_count"]})
    passing = all(r["hash_matches"] and r["row_count_matches"] for r in report)
    print(json.dumps({"status": "PASS" if passing else "FAIL",
         "data_release_id": manifest["data_release_id"], "checks": report}, indent=2))
    return 0 if passing else 1


if __name__ == "__main__":
    raise SystemExit(main())
