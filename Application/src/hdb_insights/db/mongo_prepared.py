"""Verify A's C01/C02 release and assemble bounded document profiles."""
from __future__ import annotations

import csv
import hashlib
import heapq
import json
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from bson.int64 import Int64
from .mongo_contract import (AGE_CODES, COLUMN_MAP, CONTRACT_VERSION, DATASET_IDS, ETHNIC_CODES,
    FLAT_CODES, MODES, PROVENANCE, REGIONS, RESALE_FIELDS, SPECIAL_AREAS, SPECS, HASH_RE,
    InputError, code, decimal128, integer, json_safe, resale_business, text)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class DigestBag:
    """Order-independent content digest, using bounded chunks of row hashes.

    Hash every canonical logical record, externally sort its 32-byte hash and
    hash that sequence. Duplicate multiplicity is retained. No commutative XOR.
    """
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hdbi-digest-")
        self.pending: list[bytes] = []
        self.parts: list[Path] = []
        self.count = 0

    def add(self, value):
        encoded = json.dumps(json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.pending.append(hashlib.sha256(encoded).digest())
        self.count += 1
        if len(self.pending) >= 20000:
            self.flush()

    def flush(self):
        if self.pending:
            path = Path(self.temp.name) / str(len(self.parts))
            path.write_bytes(b"".join(sorted(self.pending)))
            self.parts.append(path)
            self.pending.clear()

    def result(self):
        self.flush()
        streams = [p.open("rb") for p in self.parts]
        try:
            digest = hashlib.sha256()
            for item in heapq.merge(*(iter(lambda s=s: s.read(32), b"") for s in streams)):
                digest.update(item)
            return {"count": self.count, "sha256": digest.hexdigest()}
        finally:
            for stream in streams:
                stream.close()
            self.temp.cleanup()


ROOT_KEYS = "contract_version transform_version snapshot_id data_release_id generated_at_utc python_version package_versions code_revision sources outputs validation_summary unresolved_decisions".split()
SOURCE_KEYS = "dataset_id source_filename source_sha256 row_count headers source_url metadata_status".split()
OUTPUT_KEYS = "filename schema_id output_sha256 row_count logical_key source_ids warning_count rejected_count readiness".split()
CHECK_KEYS = "check_id dataset_id status observed expected evidence_path".split()
REFERENCE_HASHES = (
    "1af5137b8ea8ce39b45c1cac796377359fb315626fcff422371a854fe067265d",
    "76703160f94c4cf20aac4beee9de3b505edba5aa1aa99ee69a399a6c8b1e6c09",
    "df02fb469ff7a5793004636d80370a4f4a6a01c03116e3b4fc5fd1ebfc11ab23",
    "506f0e7467f5a83180bcfcf23eae3d86a8fd6b1bb06716f0b0af9f3a4cf904a6",
    "c6d9ea399fe3de82058b421d77b3a3486f5906794bd11d31e8e805ae9c29ec20",
    "97ab832982fa38e140be07a8fb015cdadb0c3f177d486213edac2607b94198d9",
    "468774fecbe508de622a9792aa89a819e25762ec5ed6f2ec11480bf35fa7bdf9",
    "5a2fa157e0dc8d7df17813f0a1baab2be68f9985ed2e0c9badef761aaba33735")
REFERENCE_ROWS = (240468, 63, 21, 18, 45, 15, 12, 48)


def exact_keys(value, keys, name):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise InputError(f"{name}: fields do not match HDBI-1.0.0")


def nonnegative(value, name):
    return integer(value, name, maximum=2**63-1)


def hash_text(value, name):
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise InputError(f"{name}: expected a full lowercase SHA-256")


def strings(value, name):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        raise InputError(f"{name}: expected a list of strings")


def validate_manifest(manifest):
    exact_keys(manifest, ROOT_KEYS, "manifest")
    if manifest["contract_version"] != CONTRACT_VERSION:
        raise InputError("Manifest contract version is incompatible")
    if not isinstance(manifest["transform_version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", manifest["transform_version"]):
        raise InputError("Invalid transform version")
    for field in ("snapshot_id",):
        hash_text(manifest[field], field)
    text(manifest["python_version"], "python_version")
    if not isinstance(manifest["package_versions"], dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in manifest["package_versions"].items()):
        raise InputError("package_versions must map names to version strings")
    if manifest["code_revision"] is not None:
        text(manifest["code_revision"], "code_revision")
    strings(manifest["unresolved_decisions"], "unresolved_decisions")
    try:
        stamp = datetime.fromisoformat(manifest["generated_at_utc"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError()
    except (TypeError, AttributeError, ValueError):
        raise InputError("generated_at_utc must be an ISO UTC timestamp") from None
    if not isinstance(manifest["sources"], list) or len(manifest["sources"]) != 8 or not isinstance(manifest["outputs"], list) or len(manifest["outputs"]) != 8:
        raise InputError("Complete publication requires all eight sources and outputs")
    for dataset, source, output in zip(DATASET_IDS, manifest["sources"], manifest["outputs"]):
        exact_keys(source, SOURCE_KEYS, dataset+" source")
        exact_keys(output, OUTPUT_KEYS, dataset+" output")
        spec = SPECS[dataset]
        if source["dataset_id"] != dataset or source["metadata_status"] not in ("verified", "partial", "unresolved"):
            raise InputError("Missing or out-of-order source")
        text(source["source_filename"], "source_filename")
        hash_text(source["source_sha256"], "source_sha256")
        nonnegative(source["row_count"], "source row_count")
        reference_index = int(dataset[1:])-1
        if source["source_sha256"] == REFERENCE_HASHES[reference_index] and source["row_count"] != REFERENCE_ROWS[reference_index]:
            raise InputError(f"{dataset}: row count contradicts the packet's matching raw hash")
        strings(source["headers"], "source headers")
        if not source["headers"]:
            raise InputError("Source headers are required")
        if source["source_url"] is not None:
            text(source["source_url"], "source_url")
        if output["filename"] != spec.filename or output["schema_id"] != "C01-"+dataset or output["logical_key"] != list(spec.logical_key) or output["source_ids"] != [dataset]:
            raise InputError(f"{dataset}: output contract mismatch")
        hash_text(output["output_sha256"], "output_sha256")
        for field in ("row_count", "warning_count", "rejected_count"):
            nonnegative(output[field], field)
        if output["readiness"] not in ("ready", "ready_with_warnings"):
            raise InputError(f"{dataset}: output is not ready")
        if output["row_count"] != source["row_count"] * (30 if dataset == "D08" else 1):
            raise InputError(f"{dataset}: complete source-row accounting failed")
    expected_snapshot = hashlib.sha256("".join(s["dataset_id"]+":"+s["source_sha256"]+"\n" for s in manifest["sources"]).encode()).hexdigest()
    expected_release = expected_snapshot[:12]+"_c1.0.0_t"+manifest["transform_version"]
    if manifest["snapshot_id"] != expected_snapshot or manifest["data_release_id"] != expected_release:
        raise InputError("Snapshot/release identity does not match the source hashes")
    summary = manifest["validation_summary"]
    exact_keys(summary, ("error_count", "warning_count", "checks"), "validation_summary")
    nonnegative(summary["error_count"], "error_count")
    nonnegative(summary["warning_count"], "warning_count")
    if summary["error_count"] or not isinstance(summary["checks"], list):
        raise InputError("Release has validation errors")
    for check in summary["checks"]:
        exact_keys(check, CHECK_KEYS, "CheckResult")
        text(check["check_id"], "check_id")
        if check["dataset_id"] is not None and check["dataset_id"] not in DATASET_IDS:
            raise InputError("Invalid check dataset")
        if check["status"] not in ("PASS", "WARN", "NOT_RUN"):
            raise InputError("Release contains a failed/invalid check")
        if check["evidence_path"] is not None:
            text(check["evidence_path"], "evidence_path")


def provenance(row):
    return {key: row[key] for key in PROVENANCE}


class PreparedRelease:
    def __init__(self, directory):
        self.directory = Path(directory).resolve(strict=True)
        manifest_path = self.path("manifest.json")
        self.manifest_hash = sha256(manifest_path)
        try:
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise InputError("Manifest must be valid UTF-8 JSON") from None
        validate_manifest(self.manifest)
        self.sources = {s["dataset_id"]: s for s in self.manifest["sources"]}
        self.outputs = dict(zip(DATASET_IDS, self.manifest["outputs"]))
        self.is_fixture = (self.manifest["code_revision"] == "TEST_FIXTURE_ONLY"
            or (self.directory/"TEST_FIXTURE_ONLY.txt").exists()
            or any("TEST_FIXTURE_ONLY" in item for item in self.manifest["unresolved_decisions"]))
        self.small_rows = {}
        self.documents = {}
        self.fact_digests = {}
        self.collection_digests = {}
        self.validated = False

    def path(self, filename):
        path = (self.directory / filename).resolve(strict=True)
        if not path.is_relative_to(self.directory) or not path.is_file():
            raise InputError("Release file escapes its directory or is not a file")
        return path

    def typed_rows(self, dataset):
        spec = SPECS[dataset]
        source = self.sources[dataset]
        with self.path(spec.filename).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if tuple(reader.fieldnames or ()) != spec.headers:
                raise InputError(f"{dataset}: wrong CSV header/order")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise InputError(f"{dataset}: malformed CSV row")
                locator = integer(row["source_row_number"], "source_row_number", 1, source["row_count"], csv=True)
                if row["dataset_id"] != dataset or row["source_file_sha256"] != source["source_sha256"]:
                    raise InputError(f"{dataset} row {locator}: provenance hash/dataset mismatch")
                prov = {"dataset_id": dataset, "source_file_sha256": source["source_sha256"], "source_row_number": locator}
                if dataset == "D01":
                    business = resale_business({key: row[key] for key in RESALE_FIELDS}, csv=True, with_identity=True)
                    if locator > 999999999 or business["record_id"] != f"D01:{source['source_sha256']}:{locator:09d}":
                        raise InputError(f"D01 row {locator}: record identity mismatch")
                    yield {**business, **prov}
                    continue
                result = {"survey_year": integer(row["survey_year"], "survey_year", 1, 9999, csv=True), **prov}
                if dataset == "D08":
                    result.update({key: text(row[key], key) for key in ("workplace_area", "workplace_area_kind", "residence_region_code", "transport_mode_code", "count_status", "source_column")})
                    area = result["workplace_area"]
                    kind = "total" if area == "Total" else "special" if area in SPECIAL_AREAS else "planning_area"
                    pair = (result["residence_region_code"], result["transport_mode_code"])
                    if result["survey_year"] != 2020 or result["workplace_area_kind"] != kind or pair not in COLUMN_MAP or result["source_column"] != COLUMN_MAP[pair]:
                        raise InputError(f"D08 row {locator}: year, area kind or source-column map mismatch")
                    if row["count_status"] == "reported":
                        result["count"] = Int64(integer(row["count"], "count", 0, 2**63-1, csv=True))
                    elif row["count_status"] == "unresolved_dash" and row["count"] == "":
                        result["count"] = None
                    else:
                        raise InputError(f"D08 row {locator}: invalid count/status pair")
                else:
                    category = "flat_type_code" if dataset in ("D02", "D03", "D04") else "ethnic_group_code"
                    allowed = FLAT_CODES if category == "flat_type_code" else ETHNIC_CODES
                    if dataset not in ("D04", "D07"):
                        allowed = (*allowed, "ALL")
                    result[category] = code(row[category], allowed, category)
                    if dataset in ("D02", "D05"):
                        result["age_group_code"] = code(row["age_group_code"], AGE_CODES, "age_group_code")
                        result["percentage"] = decimal128(row["percentage"], "percentage", 5)
                        if result["percentage"].to_decimal() > 100:
                            raise InputError("Percentage must not exceed 100")
                    elif dataset in ("D03", "D06"):
                        result.update({key: decimal128(row[key], key, 5) for key in ("average_age", "median_age")})
                    else:
                        result["population_15_plus"] = Int64(integer(row["population_15_plus"], "population_15_plus", 0, 2**63-1, csv=True))
                yield result

    def preflight(self):
        resale_docs = DigestBag()
        for dataset in DATASET_IDS:
            path = self.path(SPECS[dataset].filename)
            if sha256(path) != self.outputs[dataset]["output_sha256"]:
                raise InputError(f"{dataset}: prepared file hash mismatch")
            with path.open("rb") as stream:
                first = stream.read(3)
                if first == b"\xef\xbb\xbf":
                    raise InputError(f"{dataset}: UTF-8 BOM forbidden")
                stream.seek(0)
                if any(b"\r" in block for block in iter(lambda: stream.read(1024*1024), b"")):
                    raise InputError(f"{dataset}: LF line endings required")
            bag = DigestBag()
            keys, locators, rows = set(), Counter(), []
            for row in self.typed_rows(dataset):
                key = tuple(row[key] for key in SPECS[dataset].logical_key)
                # D01 uniqueness is checked on its compact source-row index.
                if dataset == "D01":
                    if locators[row["source_row_number"]]:
                        raise InputError("D01: duplicate source identity")
                    resale_docs.add({"_id": row["record_id"], **row})
                else:
                    if key in keys:
                        raise InputError(f"{dataset}: duplicate logical key")
                    keys.add(key)
                    rows.append(row)
                locators[row["source_row_number"]] += 1
                bag.add(row)
            expected_repeats = 30 if dataset == "D08" else 1
            if len(locators) != self.sources[dataset]["row_count"] or any(v != expected_repeats for v in locators.values()):
                raise InputError(f"{dataset}: source-row coverage mismatch")
            result = bag.result()
            if result["count"] != self.outputs[dataset]["row_count"]:
                raise InputError(f"{dataset}: declared row count mismatch")
            self.fact_digests[dataset] = result
            if dataset != "D01":
                self.small_rows[dataset] = rows
        self.collection_digests["resale_transactions"] = resale_docs.result()
        self.documents["source_datasets"] = [{"_id": dataset, "source_filename": self.sources[dataset]["source_filename"], "source_file_sha256": self.sources[dataset]["source_sha256"], "source_row_count": self.sources[dataset]["row_count"]} for dataset in DATASET_IDS]
        self.documents["demographic_profiles"] = assemble_demographics(self.small_rows)
        self.documents["mobility_profiles"] = assemble_mobility(self.small_rows["D08"])
        for name, docs in self.documents.items():
            bag = DigestBag()
            for doc in docs:
                bag.add(doc)
            self.collection_digests[name] = bag.result()
        if tuple(self.sources[dataset]["source_sha256"] for dataset in DATASET_IDS) == REFERENCE_HASHES:
            profiles = self.documents["demographic_profiles"]
            mobility = self.documents["mobility_profiles"]
            if (len(profiles), len(mobility), sum(len(doc["source_rows"]) for doc in profiles),
                sum(len(doc["age_distribution"]) for doc in profiles),
                sum(obs["count"] is None for doc in mobility for obs in doc["observations"])) != (36, 48, 174, 108, 73):
                raise InputError("Profile controls contradict the packet's matching full source snapshot")
        # Do not accept a file changed between hashing and parsing.
        self.check_unchanged()
        self.validated = True
        return self.report()

    def check_unchanged(self):
        if sha256(self.path("manifest.json")) != self.manifest_hash:
            raise InputError("Manifest changed during the operation")
        for dataset in DATASET_IDS:
            if sha256(self.path(SPECS[dataset].filename)) != self.outputs[dataset]["output_sha256"]:
                raise InputError(f"{dataset}: file changed during the operation")

    def report(self):
        return {"contract_version": CONTRACT_VERSION, "data_release_id": self.manifest["data_release_id"],
            "dataset_kind": "TEST_FIXTURE_ONLY" if self.is_fixture else "prepared_source",
            "fact_digests": self.fact_digests, "collection_digests": self.collection_digests,
            "warning_count": self.manifest["validation_summary"]["warning_count"],
            "preparation_validation_summary": self.manifest["validation_summary"],
            "output_readiness": [{key: output[key] for key in ("filename", "readiness", "warning_count", "rejected_count")} for output in self.manifest["outputs"]],
            "unresolved_decisions": self.manifest["unresolved_decisions"],
            "database_load": "NOT_RUN"}


def assemble_demographics(rows_by_dataset):
    profiles = []
    for group_type, category, age_id, stats_id, pop_id in (
        ("flat_type", "flat_type_code", "D02", "D03", "D04"),
        ("ethnicity", "ethnic_group_code", "D05", "D06", "D07")):
        ages, stats, populations = defaultdict(list), {}, {}
        for row in rows_by_dataset[age_id]:
            ages[(row["survey_year"], row[category])].append(row)
        for row in rows_by_dataset[stats_id]:
            key = (row["survey_year"], row[category])
            if key in stats:
                raise InputError("Conflicting demographic statistics key")
            stats[key] = row
        for row in rows_by_dataset[pop_id]:
            key = (row["survey_year"], row[category])
            if key in populations:
                raise InputError("Conflicting demographic population key")
            populations[key] = row
        if set(ages) != set(stats) or set(populations) != {key for key in ages if key[1] != "ALL"}:
            raise InputError("Demographic age/statistics/population coverage mismatch")
        for (year, group), age_rows in sorted(ages.items()):
            by_age = {row["age_group_code"]: row for row in age_rows}
            if len(age_rows) != 3 or set(by_age) != set(AGE_CODES):
                raise InputError("Demographic profile requires exactly three unique age groups")
            statistic = stats[(year, group)]
            population = populations.get((year, group))
            contributing = [*age_rows, statistic, *([population] if population else [])]
            refs = [provenance(row) for row in contributing]
            refs.sort(key=lambda row: (row["dataset_id"], row["source_row_number"]))
            profiles.append({"_id": f"{group_type}:{group}:{year}", "group_type": group_type,
                "group_code": group, "survey_year": year, "average_age": statistic["average_age"],
                "median_age": statistic["median_age"], "population_15_plus": population["population_15_plus"] if population else None,
                "population_status": "reported" if population else "not_provided",
                "age_distribution": [{"age_group_code": age, "percentage": by_age[age]["percentage"]} for age in AGE_CODES], "source_rows": refs})
    return profiles


def assemble_mobility(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["survey_year"], row["workplace_area"])].append(row)
    documents = []
    for (year, area), records in sorted(groups.items()):
        by_pair = {(row["residence_region_code"], row["transport_mode_code"]): row for row in records}
        locator = provenance(records[0])
        kind = records[0]["workplace_area_kind"]
        if len(records) != 30 or set(by_pair) != set(COLUMN_MAP) or any(provenance(row) != locator or row["workplace_area_kind"] != kind for row in records):
            raise InputError("Mobility profile needs 30 unique pairs with one consistent source row")
        observations = [{key: by_pair[pair][key] for key in ("residence_region_code", "transport_mode_code", "count", "count_status", "source_column")} for pair in COLUMN_MAP]
        documents.append({"_id": f"{year}:{area}", "survey_year": year, "workplace_area": area,
            "workplace_area_kind": kind, "observations": observations, **locator})
    return documents


def document_digests(db, names):
    result = {}
    for kind, name in names.items():
        if kind == "application_metadata":
            continue
        bag = DigestBag()
        for doc in db[name].find({}).batch_size(500):
            bag.add(doc)
        result[kind] = bag.result()
    return result


def expand_demographic(release, documents):
    """Restore C01 fact grain using A's verified logical-key/row lookup.

    C04 stores group-level source_rows, rather than a locator on each embedded
    age item. Do not infer the age/locator association from array position.
    The validated prepared release supplies that association for reconciliation.
    """
    indices = {dataset: {tuple(row[key] for key in SPECS[dataset].logical_key): row
        for row in release.small_rows[dataset]} for dataset in ("D02", "D03", "D04", "D05", "D06", "D07")}
    for doc in documents:
        if doc["group_type"] == "flat_type":
            category, age_id, stats_id, pop_id = "flat_type_code", "D02", "D03", "D04"
        elif doc["group_type"] == "ethnicity":
            category, age_id, stats_id, pop_id = "ethnic_group_code", "D05", "D06", "D07"
        else:
            raise InputError("Unknown stored demographic dimension")
        year, group = doc["survey_year"], doc["group_code"]
        used_refs = []
        def ref(dataset, key):
            original = indices[dataset].get(key)
            if original is None:
                raise InputError("Stored demographic key does not exist in prepared input")
            locator = provenance(original)
            if locator not in doc["source_rows"]:
                raise InputError("Stored demographic provenance is missing its prepared-row reference")
            used_refs.append(locator)
            return locator
        for age in doc["age_distribution"]:
            yield age_id, {"survey_year": year, category: group, "age_group_code": age["age_group_code"],
                "percentage": age["percentage"], **ref(age_id, (year, group, age["age_group_code"]))}
        yield stats_id, {"survey_year": year, category: group, "average_age": doc["average_age"],
            "median_age": doc["median_age"], **ref(stats_id, (year, group))}
        if group != "ALL":
            yield pop_id, {"survey_year": year, category: group, "population_15_plus": doc["population_15_plus"],
                **ref(pop_id, (year, group))}
        used_refs.sort(key=lambda row: (row["dataset_id"], row["source_row_number"]))
        if used_refs != doc["source_rows"]:
            raise InputError("Stored demographic source references are duplicated, unordered or unused")


def expand_mobility(documents):
    for doc in documents:
        for observation in doc["observations"]:
            yield "D08", {"survey_year": doc["survey_year"], "workplace_area": doc["workplace_area"],
                "workplace_area_kind": doc["workplace_area_kind"], **observation, **provenance(doc)}


def verify_loaded(release, db, names):
    """Full document digests include every fact and every provenance reference.

    Comparing typed expected profiles to stored profiles also reconciles all six
    demographic inputs without pretending the aggregate arrays are SQL FKs.
    """
    observed = document_digests(db, names)
    if observed != release.collection_digests:
        raise InputError("Stored document content/counts do not reconcile to the prepared release")
    bags = {dataset: DigestBag() for dataset in DATASET_IDS}
    for doc in db[names["resale_transactions"]].find({}).batch_size(500):
        bags["D01"].add({key: value for key, value in doc.items() if key != "_id"})
    for dataset, row in expand_demographic(release, db[names["demographic_profiles"]].find({})):
        bags[dataset].add(row)
    for dataset, row in expand_mobility(db[names["mobility_profiles"]].find({})):
        bags[dataset].add(row)
    expanded = {dataset: bag.result() for dataset, bag in bags.items()}
    if expanded != release.fact_digests:
        raise InputError("Expanded canonical fact digests do not reconcile to the prepared release")
    return observed
