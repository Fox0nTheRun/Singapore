"""Candidate workload indexes. Performance benefits require measured evidence."""
from pymongo import ASCENDING, IndexModel

INDEXES = {
    "source_datasets": [],
    "resale_transactions": [
        IndexModel([(k, ASCENDING) for k in ("town_name", "flat_type_code", "registration_month", "record_id")], name="resale_town_type_month_id"),
        IndexModel([(k, ASCENDING) for k in ("registration_month", "record_id")], name="resale_month_id"),
    ],
    "demographic_profiles": [IndexModel([(k, ASCENDING) for k in ("group_type", "group_code", "survey_year")], name="demographic_natural_key", unique=True)],
    "mobility_profiles": [IndexModel([("survey_year", ASCENDING), ("workplace_area", ASCENDING)], name="mobility_natural_key", unique=True)],
    "application_metadata": [], "demo_resale_transactions": [],
}


def create_indexes(collection, kind):
    if INDEXES[kind]:
        collection.create_indexes(INDEXES[kind])


def check_indexes(collection, kind):
    actual = collection.index_information()
    for model in INDEXES[kind]:
        expected = model.document
        found = actual.get(expected["name"], {})
        if list(found.get("key", [])) != list(expected["key"].items()) or bool(found.get("unique", False)) != bool(expected.get("unique", False)):
            raise ValueError(f"{collection.name}: required candidate index missing or changed")


def explain_find(db, collection_name, predicate, limit=50):
    return db.command({"explain": {"find": collection_name, "filter": predicate,
        "sort": {"registration_month": 1, "record_id": 1}, "limit": limit}, "verbosity": "executionStats"})


def explain_pipeline(db, collection_name, pipeline):
    return db.command({"explain": {"aggregate": collection_name, "pipeline": pipeline, "cursor": {}}, "verbosity": "executionStats"})
