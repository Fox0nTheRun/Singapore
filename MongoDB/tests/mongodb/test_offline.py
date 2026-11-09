"""Parser/assembler controls; these do NOT prove MongoDB execution."""
import csv
import inspect
import json
from copy import deepcopy
from decimal import Decimal
import pytest
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from hdb_insights.db.mongo_contract import (InputError, decimal128, decimal_text, integer,
    json_safe, month, resale_filter, SPECS)
from hdb_insights.db.mongo_loader import publish_release
from hdb_insights.db.mongo_prepared import (DigestBag, PreparedRelease, assemble_demographics,
    assemble_mobility, expand_demographic, expand_mobility, sha256, validate_manifest)
from hdb_insights.db.mongodb_adapter import MongoDBAdapter


@pytest.mark.parametrize("value,expected", [("2.345", "2.35"), ("2.355", "2.36"), ("-2.345", "-2.35"), ("2.344999999999999", "2.34"), ("0", "0.00")])
def test_half_up(value, expected):
    assert decimal_text(Decimal128(value)) == expected


@pytest.mark.parametrize("value", [True, 1.5, "1e3", "NaN", "Infinity", "1.001", "1.000", "1000000.00", "-1", "0", ""])
def test_price_area_reject_precision_and_bad_types(value):
    with pytest.raises(InputError):
        decimal128(value, "floor_area_sqm", 8, positive=True)


def test_exact_types_and_maximum():
    assert decimal128("999999999999.99", "resale_price", 14).to_decimal() == Decimal("999999999999.99")
    with pytest.raises(InputError):
        integer(True, "year")
    with pytest.raises(InputError):
        integer("1.0", "count", csv=True)
    assert json_safe({"count": Int64(0), "unknown": None, "price": Decimal128("12.3")}) == {"count": 0, "unknown": None, "price": "12.30"}


@pytest.mark.parametrize("bad", [{"$where": "evil"}, {"town_name": {"$ne": ""}}, {"flat_type_code": "ALL"}, {"start_month": "2020-13"}, {"start_month": "0000-01"}, {"start_month": "2020-02", "end_month": "2020-01"}, {"town_name": ""}])
def test_filters_reject_injection_and_bad_months(bad):
    with pytest.raises(InputError):
        resale_filter(bad)


def test_inclusive_optional_filters_and_signature():
    assert resale_filter({"start_month": "2020-01", "end_month": "2020-02", "flat_type_code": None}) == {"registration_month": {"$gte": "2020-01", "$lte": "2020-02"}}
    assert list(inspect.signature(MongoDBAdapter.search_resale).parameters) == ["self", "filters", "limit", "offset"]


def test_fixture_roundtrip_and_duplicates(release):
    assert release.is_fixture
    assert release.collection_digests["source_datasets"]["count"] == 8
    assert release.collection_digests["resale_transactions"]["count"] == 3
    profiles = release.documents["demographic_profiles"]
    assert len(profiles) == 4
    assert sum(len(row["source_rows"]) for row in profiles) == 18
    assert sum(len(row["age_distribution"]) for row in profiles) == 12
    assert all(row["population_15_plus"] is None for row in profiles if row["group_code"] == "ALL")
    resale = list(release.typed_rows("D01"))
    assert resale[0]["record_id"] != resale[1]["record_id"]
    assert resale[0]["resale_price"] == resale[1]["resale_price"]
    observations = release.documents["mobility_profiles"][0]["observations"]
    assert len(observations) == 30
    assert sum(row["count"] is None for row in observations) == 1
    assert any(row["count"] == 0 and row["count_status"] == "reported" for row in observations)


def test_missing_population_and_duplicate_array_keys(release):
    rows = deepcopy(release.small_rows)
    rows["D04"] = []
    with pytest.raises(InputError):
        assemble_demographics(rows)
    rows = deepcopy(release.small_rows["D08"])
    rows[-1] = {**rows[-2], "count": Int64(999)}
    with pytest.raises(InputError):
        assemble_mobility(rows)


@pytest.mark.parametrize("mutation", ["blocked", "snapshot", "version", "missing_output", "bad_source_count", "extra_key", "validation_failure"])
def test_manifest_rejects_incomplete_or_incompatible(release, mutation):
    manifest = deepcopy(release.manifest)
    if mutation == "blocked": manifest["outputs"][0]["readiness"] = "blocked"
    if mutation == "snapshot": manifest["snapshot_id"] = "0"*64
    if mutation == "version": manifest["contract_version"] = "HDBI-2.0.0"
    if mutation == "missing_output": manifest["outputs"].pop()
    if mutation == "bad_source_count": manifest["sources"][0]["row_count"] = True
    if mutation == "extra_key": manifest["helpful_extra"] = 1
    if mutation == "validation_failure": manifest["validation_summary"]["checks"][0]["status"] = "FAIL"
    with pytest.raises(InputError):
        validate_manifest(manifest)


def rewrite_csv(release, dataset, mutate):
    path = release.directory/SPECS[dataset].filename
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        headers, rows = list(reader.fieldnames), list(reader)
    headers, rows = mutate(headers, rows)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    manifest = deepcopy(release.manifest)
    manifest["outputs"][int(dataset[1:])-1]["output_sha256"] = sha256(path)
    (release.directory/"manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_file_hash_detects_tampering(release):
    path = release.directory/"resale.csv"
    path.write_bytes(path.read_bytes().replace(b"100.00", b"101.00", 1))
    with pytest.raises(InputError, match="hash mismatch"):
        PreparedRelease(release.directory).preflight()


@pytest.mark.parametrize("case", ["header", "precision", "identity", "dataset", "null_status"])
def test_resealed_bad_csv_still_rejected(release, case):
    dataset = "D08" if case == "null_status" else "D01"
    def mutate(headers, rows):
        if case == "header": headers[0], headers[1] = headers[1], headers[0]
        if case == "precision": rows[0]["resale_price"] = "100.001"
        if case == "identity": rows[0]["record_id"] = rows[1]["record_id"]
        if case == "dataset": rows[0]["dataset_id"] = "D02"
        if case == "null_status": rows[0]["count"] = ""
        return headers, rows
    rewrite_csv(release, dataset, mutate)
    with pytest.raises(InputError):
        PreparedRelease(release.directory).preflight()


def test_same_release_content_change_is_visible(release):
    original_digest = deepcopy(release.collection_digests)
    def mutate(headers, rows):
        rows[0]["resale_price"] = "101.00"
        return headers, rows
    rewrite_csv(release, "D01", mutate)
    changed = PreparedRelease(release.directory)
    changed.preflight()
    assert changed.manifest["data_release_id"] == release.manifest["data_release_id"]
    assert changed.collection_digests != original_digest


def test_multiset_digest_order_and_duplicate_multiplicity():
    results = []
    for rows in (({"a": 1}, {"a": 2}), ({"a": 2}, {"a": 1}), ({"a": 1}, {"a": 2}, {"a": 2})):
        bag = DigestBag()
        for row in rows: bag.add(row)
        results.append(bag.result())
    assert results[0] == results[1]
    assert results[1] != results[2]


def test_no_fixture_publication_even_with_maintenance(release):
    with pytest.raises(InputError, match="fixtures"):
        publish_release(release, None, {}, "never_written.json", "test", maintenance_confirmed=True)


def test_expanded_profiles_restore_every_canonical_fact(release):
    bags = {dataset: DigestBag() for dataset in release.small_rows}
    for dataset, row in expand_demographic(release, release.documents["demographic_profiles"]):
        bags[dataset].add(row)
    for dataset, row in expand_mobility(release.documents["mobility_profiles"]):
        bags[dataset].add(row)
    assert {dataset: bag.result() for dataset, bag in bags.items()} == {dataset: digest for dataset, digest in release.fact_digests.items() if dataset != "D01"}


def test_age_lineage_is_not_inferred_from_array_order(release):
    rows = release.small_rows["D02"]
    rows[0]["source_row_number"], rows[2]["source_row_number"] = rows[2]["source_row_number"], rows[0]["source_row_number"]
    docs = assemble_demographics(release.small_rows)
    expanded = [row for dataset, row in expand_demographic(release, docs) if dataset == "D02" and row["flat_type_code"] == "4_ROOM" and row["age_group_code"] == "BELOW_15"]
    assert expanded[0]["source_row_number"] == 3
