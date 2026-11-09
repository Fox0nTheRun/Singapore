"""Real-server tests. All writes are randomly prefixed in hdb_insights_demo.

Skipped without TWO explicit opt-ins. They never fall back to a mock server.
"""
import json
from copy import deepcopy
from decimal import Decimal, localcontext
import pytest
from bson.decimal128 import Decimal128
from bson.int64 import Int64
from pymongo.errors import WriteError
from hdb_insights.db.mongo_contract import InputError, decimal_text
from hdb_insights.db.mongo_indexes import explain_find, explain_pipeline
from hdb_insights.db.mongo_loader import stage_release, verify_schema_and_indexes
from hdb_insights.db.mongo_prepared import verify_loaded
from hdb_insights.db.mongo_queries import resale_summary_pipeline
from hdb_insights.db.mongodb_adapter import MongoDBAdapter, proposed_options_formatter


def distinct_resale(case):
    row = deepcopy(next(case["release"].typed_rows("D01")))
    row["source_row_number"] = 9999
    row["record_id"] = row["record_id"][:-9]+"000009999"
    return {"_id": row["record_id"], **row}


def test_T_C_01_types_and_installed_schema(mongo_case):
    case = mongo_case
    verify_schema_and_indexes(case["db"], case["names"])
    row = next(case["adapter"].collection("resale_transactions").aggregate([
        {"$project": {"price_type": {"$type": "$resale_price"}, "year_type": {"$type": "$lease_commence_year"}}}]))
    assert row["price_type"] == "decimal" and row["year_type"] == "int"
    row = next(case["adapter"].collection("demographic_profiles").aggregate([
        {"$match": {"group_code": "4_ROOM"}}, {"$project": {"population_type": {"$type": "$population_15_plus"}}}]))
    assert row["population_type"] == "long"


@pytest.mark.parametrize("field,value", [("resale_price", "100.00"), ("resale_price", 100.0), ("resale_price", Decimal128("0")),
    ("resale_price", Decimal128("NaN")), ("resale_price", Decimal128("Infinity")),
    ("floor_area_sqm", Decimal128("1.001")), ("registration_month", "2020-13"),
    ("registration_month", "0000-01"), ("flat_type_code", "ALL"), ("storey_lower", 9),
    ("lease_commence_year", True), ("_id", "wrong")])
def test_T_C_02_direct_invalid_insert(mongo_case, field, value):
    doc = distinct_resale(mongo_case)
    doc[field] = value
    with pytest.raises(WriteError) as exc:
        mongo_case["adapter"].collection("resale_transactions").insert_one(doc)
    assert exc.value.code == 121


def test_T_C_02_direct_invalid_update(mongo_case):
    coll = mongo_case["adapter"].collection("resale_transactions")
    identity = coll.find_one()["_id"]
    with pytest.raises(WriteError) as exc:
        coll.update_one({"_id": identity}, {"$set": {"storey_lower": 4, "storey_upper": 3}})
    assert exc.value.code == 121


@pytest.mark.parametrize("which", ["age_duplicate", "mobility_duplicate", "null_status", "all_population", "malformed_array"])
def test_T_C_03_embedded_constraints(mongo_case, which):
    adapter = mongo_case["adapter"]
    if which in ("age_duplicate", "all_population"):
        coll = adapter.collection("demographic_profiles")
        doc = coll.find_one({"group_code": "ALL"} if which == "all_population" else {"group_code": "4_ROOM"})
        if which == "age_duplicate":
            doc["age_distribution"][2]["age_group_code"] = doc["age_distribution"][0]["age_group_code"]
            doc["age_distribution"][2]["percentage"] = Decimal128("99.00")
        else:
            doc["population_15_plus"], doc["population_status"] = Int64(0), "reported"
    else:
        coll = adapter.collection("mobility_profiles")
        doc = coll.find_one()
        if which == "mobility_duplicate":
            doc["observations"][1] = {**doc["observations"][0], "count": Int64(999)}
        elif which == "null_status":
            doc["observations"][0]["count"] = None
        else:
            doc["observations"] = "not an array"
    with pytest.raises(WriteError) as exc:
        coll.replace_one({"_id": doc["_id"]}, doc)
    assert exc.value.code == 121


def test_T_C_05_06_reconciliation_and_content_drift(mongo_case):
    names = {kind: name for kind, name in mongo_case["names"].items() if kind not in ("application_metadata", "demo_resale_transactions")}
    verify_loaded(mongo_case["release"], mongo_case["db"], names)
    coll = mongo_case["adapter"].collection("resale_transactions")
    identity = coll.find_one()["_id"]
    coll.update_one({"_id": identity}, {"$set": {"resale_price": Decimal128("999.00")}})
    with pytest.raises(InputError, match="reconcile"):
        verify_loaded(mongo_case["release"], mongo_case["db"], names)


def test_T_C_08_search_and_validation(mongo_case):
    adapter = mongo_case["adapter"]
    first = adapter.search_resale({"start_month": "2020-01", "end_month": "2020-01"}, 1, 0)
    second = adapter.search_resale({"start_month": "2020-01", "end_month": "2020-01"}, 1, 1)
    assert first["ok"] and second["ok"] and first["data"]["total_count"] == 2
    assert first["data"]["rows"][0]["record_id"] < second["data"]["rows"][0]["record_id"]
    assert adapter.search_resale({}, 50, 999)["data"]["rows"] == []
    assert adapter.search_resale({"town_name": {"$ne": ""}})["error"]["code"] == "VALIDATION_ERROR"
    assert adapter.search_resale({}, True)["error"]["code"] == "VALIDATION_ERROR"
    assert adapter.list_filter_options("resale")["data"]["options"]["town_name"] == ["TEST TOWN"]


def test_T_C_09_mean_of_ratios_and_empty(mongo_case):
    adapter = mongo_case["adapter"]
    rows = list(mongo_case["release"].typed_rows("D01"))
    with localcontext() as ctx:
        ctx.prec = 50
        expected = sum(row["resale_price"].to_decimal()/row["floor_area_sqm"].to_decimal() for row in rows)/len(rows)
    raw = next(adapter.collection("resale_transactions").aggregate(resale_summary_pipeline({})))
    assert abs(raw["average_price_per_sqm"].to_decimal()-expected) <= Decimal("0.000001")
    result = adapter.summarise_resale({})
    assert result["data"]["average_price_per_sqm"] == decimal_text(expected) == "7.67"
    assert result["data"]["average_price"] == "166.67"
    empty = adapter.summarise_resale({"start_month": "2030-01"})
    assert empty["data"] == {"transaction_count": 0, "average_price": None, "average_price_per_sqm": None}
    assert [r["registration_month"] for r in adapter.resale_trend({})["data"]["rows"]] == ["2020-01", "2020-02"]


def test_T_C_09_database_exact_tie_rounds_half_up(mongo_case):
    coll = mongo_case["adapter"].collection("resale_transactions")
    for locator, price in ((8001, "2.34"), (8002, "2.35")):
        row = distinct_resale(mongo_case)
        row.update(_id=row["_id"][:-9]+f"{locator:09d}", record_id=row["record_id"][:-9]+f"{locator:09d}",
            source_row_number=locator, town_name="TIE TOWN", resale_price=Decimal128(price), floor_area_sqm=Decimal128("1.00"))
        coll.insert_one(row)
    assert mongo_case["adapter"].summarise_resale({"town_name": "TIE TOWN"})["data"]["average_price"] == "2.35"


def test_T_C_10_demographic_all_missing_and_denominators(mongo_case):
    adapter = mongo_case["adapter"]
    ordinary = adapter.demographic_profile("flat_type", "4_ROOM", 2018)["data"]
    assert ordinary["population_15_plus"] == 1000
    assert ordinary["median_age"] == "42.00"
    assert [row["percentage"] for row in ordinary["age_distribution"]] == ["20.00", "60.00", "20.10"]
    aggregate = adapter.demographic_profile("ethnicity", "ALL", 2018)["data"]
    assert aggregate["population_15_plus"] is None and aggregate["population_status"] == "not_provided"
    missing = adapter.demographic_profile("flat_type", "MULTI_GENERATION", 2018)
    assert missing["ok"] and missing["data"] is None and missing["meta"]["note"]


def test_T_C_11_mobility_exact_denominator_unknown_and_zero(mongo_case):
    adapter = mongo_case["adapter"]
    all_regions = adapter.mobility_breakdown("Total", "ALL")["data"]
    assert all_regions["published_total"] == 101
    assert all_regions["rows"][0]["share_pct"] == "39.60"
    assert all_regions["rows"][3]["share_pct"] == "0.00"
    central = adapter.mobility_breakdown("Total", "CENTRAL")["data"]
    assert central["published_total"] == 50 and central["rows"][0]["share_pct"] == "10.00"
    north = adapter.mobility_breakdown("Total", "NORTH")["data"]
    assert north["rows"][0]["count"] is None and north["rows"][0]["share_pct"] is None
    east = adapter.mobility_breakdown("Total", "EAST")["data"]
    assert all(row["share_pct"] is None for row in east["rows"])
    assert adapter.mobility_breakdown("Missing fixture area", "ALL")["error"]["code"] == "DATA_NOT_READY"


def test_T_C_12_json_ready_and_missing_metadata(mongo_case):
    adapter = mongo_case["adapter"]
    for result in (adapter.search_resale({}), adapter.summarise_resale({}), adapter.demographic_profile("flat_type", "4_ROOM", 2018), adapter.mobility_breakdown("Total", "NORTH")):
        json.dumps(result, allow_nan=False)
        assert set(result) == {"ok", "data", "error", "meta"}
    adapter.collection("application_metadata").delete_one({"_id": "active"})
    result = adapter.search_resale({})
    assert result["error"]["code"] == "DATA_NOT_READY" and result["meta"]["data_release_id"] is None


def demo_payload(adapter):
    row = adapter.search_resale({}, 1)["data"]["rows"][0]
    return {"seed_record_id": row["record_id"], **{key: value for key, value in row.items() if key != "record_id"}}


def test_T_C_13_persistent_crud_and_isolation(mongo_case):
    from pymongo import MongoClient
    adapter = mongo_case["adapter"]
    before = adapter.summarise_resale({})["data"]
    created = adapter.create_demo_resale(demo_payload(adapter))
    assert created["ok"]
    identity = created["data"]["demo_record_id"]
    with MongoClient(mongo_case["uri"], serverSelectionTimeoutMS=5000) as other_client:
        other = MongoDBAdapter(other_client, "hdb_insights_demo", _test_prefix=mongo_case["prefix"])
        assert other.get_demo_resale(identity)["data"] == created["data"]
        assert other.update_demo_resale(identity, {"resale_price": "101.00"})["data"]["resale_price"] == "101.00"
        assert other.update_demo_resale(identity, {"resale_price": "101.00"})["ok"]
        for bad in ({}, {"seed_record_id": "x"}, {"$set": {}}, {"storey_lower": 10}):
            assert other.update_demo_resale(identity, bad)["error"]["code"] == "VALIDATION_ERROR"
        assert other.delete_demo_resale(identity)["data"]["deleted_count"] == 1
        assert other.get_demo_resale(identity)["error"]["code"] == "NOT_FOUND"
    assert adapter.summarise_resale({})["data"] == before


def test_T_C_13_stale_seed_release(mongo_case):
    adapter = mongo_case["adapter"]
    result = adapter.create_demo_resale(demo_payload(adapter))
    identity = result["data"]["demo_record_id"]
    adapter.demo.update_one({"_id": identity}, {"$set": {"base_data_release_id": "older_release"}})
    assert adapter.get_demo_resale(identity)["error"]["code"] == "DATA_NOT_READY"


def test_T_C_14_conflicting_update(mongo_case, monkeypatch):
    adapter = mongo_case["adapter"]
    identity = adapter.create_demo_resale(demo_payload(adapter))["data"]["demo_record_id"]
    original_read = adapter._demo_record
    def read_then_concurrent_edit(active, record_id):
        row = original_read(active, record_id)
        adapter.demo.update_one({"_id": identity}, {"$inc": {"revision": 1}})
        return row
    monkeypatch.setattr(adapter, "_demo_record", read_then_concurrent_edit)
    result = adapter.update_demo_resale(identity, {"resale_price": "999.00"})
    assert result["error"]["code"] == "CONFLICT"
    assert adapter.demo.find_one({"_id": identity})["resale_price"].to_decimal() == Decimal("100.00")


def test_T_C_16_explain_and_staged_load(mongo_case):
    adapter = mongo_case["adapter"]
    before = adapter.summarise_resale({})["data"]
    name = adapter.collection("resale_transactions").name
    plan = explain_find(mongo_case["db"], name, {})
    assert plan["ok"] == 1 and "queryPlanner" in plan
    assert explain_pipeline(mongo_case["db"], name, resale_summary_pipeline({}))["ok"] == 1
    assert adapter.summarise_resale({})["data"] == before
    run_id = mongo_case["prefix"].removeprefix("_test_").removesuffix("_")
    staged = {}
    try:
        staged = stage_release(mongo_case["release"], mongo_case["db"], run_id)
        verify_loaded(mongo_case["release"], mongo_case["db"], staged)
    finally:
        from hdb_insights.db.mongo_contract import COLLECTIONS
        for kind in COLLECTIONS:
            mongo_case["db"].drop_collection(f"_c_{run_id}_{kind}")


def test_T_C_14_uncertain_create_has_one_reconcilable_id(mongo_case, monkeypatch):
    from pymongo.errors import AutoReconnect
    from pymongo.synchronous.collection import Collection
    adapter = mongo_case["adapter"]
    original_insert = Collection.insert_one
    intended = []
    def commit_then_lose_ack(collection, document, *args, **kwargs):
        result = original_insert(collection, document, *args, **kwargs)
        if collection.full_name == adapter.demo.full_name:
            intended.append(document["_id"])
            raise AutoReconnect("TEST_ONLY simulated lost acknowledgement")
        return result
    monkeypatch.setattr(Collection, "insert_one", commit_then_lose_ack)
    result = adapter.create_demo_resale(demo_payload(adapter))
    assert not result["ok"] and result["error"]["code"] == "DB_UNAVAILABLE"
    assert len(intended) == 1 and intended[0] in result["error"]["message"]
    assert adapter.demo.count_documents({}) == 1
    assert adapter.get_demo_resale(intended[0])["ok"]
