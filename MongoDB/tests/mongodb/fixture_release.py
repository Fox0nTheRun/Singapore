"""Explicit synthetic ENGINEERING fixtures, never real HDB observations."""
import csv
import hashlib
import json
from pathlib import Path
from hdb_insights.db.mongo_contract import AGE_CODES, COLUMN_MAP, DATASET_IDS, SPECS
from hdb_insights.db.mongo_prepared import sha256


def make_fixture(destination):
    directory = Path(destination)
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {dataset: hashlib.sha256(("SYNTHETIC_TEST_FIXTURE_ONLY:"+dataset).encode()).hexdigest() for dataset in DATASET_IDS}
    rows = {}
    rows["D01"] = []
    for locator, (price, area, period) in enumerate((("100.00", "10.00", "2020-01"), ("100.00", "10.00", "2020-01"), ("300.00", "100.00", "2020-02")), 1):
        rows["D01"].append(dict(zip(SPECS["D01"].business, (f"D01:{hashes['D01']}:{locator:09d}", period, "TEST TOWN", "4_ROOM", "001A", "TEST STREET", "1", "3", area, "Fixture model", "1990", "600", price))))
    for age_id, stats_id, pop_id, field, group in (("D02", "D03", "D04", "flat_type_code", "4_ROOM"), ("D05", "D06", "D07", "ethnic_group_code", "CHINESE")):
        rows[age_id] = [{"survey_year": "2018", field: category, "age_group_code": age, "percentage": percentage} for category in (group, "ALL") for age, percentage in zip(AGE_CODES, ("20.00", "60.00", "20.10"))]
        rows[stats_id] = [{"survey_year": "2018", field: category, "average_age": "41.25", "median_age": "42.00"} for category in (group, "ALL")]
        rows[pop_id] = [{"survey_year": "2018", field: group, "population_15_plus": "1000"}]
    counts = {"ALL": (101, 40, 30, 30, 0), "CENTRAL": (50, 5, 10, 15, 20), "EAST": (0, 0, 0, 0, 0), "NORTH": (100, None, 30, 20, 0), "NORTH_EAST": (100, 10, 20, 30, 40), "WEST": (100, 10, 20, 30, 40)}
    rows["D08"] = []
    region_index = {region: 0 for region in counts}
    for (region, mode), column in COLUMN_MAP.items():
        count = counts[region][region_index[region]]
        region_index[region] += 1
        rows["D08"].append({"survey_year": "2020", "workplace_area": "Total", "workplace_area_kind": "total", "residence_region_code": region, "transport_mode_code": mode, "count": "" if count is None else str(count), "count_status": "unresolved_dash" if count is None else "reported", "source_column": column})
    sources, outputs = [], []
    for dataset in DATASET_IDS:
        spec = SPECS[dataset]
        for i, row in enumerate(rows[dataset], 1):
            row.update(dataset_id=dataset, source_file_sha256=hashes[dataset], source_row_number=str(1 if dataset == "D08" else i))
        path = directory/spec.filename
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=spec.headers, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows[dataset])
        sources.append({"dataset_id": dataset, "source_filename": f"SYNTHETIC_TEST_INPUT_{dataset}.csv", "source_sha256": hashes[dataset], "row_count": 1 if dataset == "D08" else len(rows[dataset]), "headers": ["SYNTHETIC_ENGINEERING_FIXTURE_ONLY"], "source_url": None, "metadata_status": "unresolved"})
        outputs.append({"filename": spec.filename, "schema_id": "C01-"+dataset, "output_sha256": sha256(path), "row_count": len(rows[dataset]), "logical_key": list(spec.logical_key), "source_ids": [dataset], "warning_count": 1, "rejected_count": 0, "readiness": "ready_with_warnings"})
    snapshot = hashlib.sha256("".join(dataset+":"+hashes[dataset]+"\n" for dataset in DATASET_IDS).encode()).hexdigest()
    release_id = snapshot[:12]+"_c1.0.0_t0.1.0"
    manifest = {"contract_version": "HDBI-1.0.0", "transform_version": "0.1.0", "snapshot_id": snapshot,
        "data_release_id": release_id, "generated_at_utc": "2026-10-24T00:00:00Z", "python_version": "fixture",
        "package_versions": {}, "code_revision": "TEST_FIXTURE_ONLY", "sources": sources, "outputs": outputs,
        "validation_summary": {"error_count": 0, "warning_count": 8, "checks": [{"check_id": "FIXTURE_LABEL", "dataset_id": None, "status": "WARN", "observed": "Synthetic engineering fixture", "expected": "Not source data", "evidence_path": None}]},
        "unresolved_decisions": ["TEST_FIXTURE_ONLY: not real HDB data; never publish as an analytical release", "DEC-01: unresolved mobility dash"]}
    (directory/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    (directory/"TEST_FIXTURE_ONLY.txt").write_text("Synthetic engineering fixtures. Hashes identify fixture labels, not supplied raw HDB files. Not for analytical publication.\n", encoding="utf-8")
    return directory
