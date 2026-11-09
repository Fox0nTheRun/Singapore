import os
import sys
import uuid
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_release import make_fixture
from hdb_insights.db.mongo_prepared import PreparedRelease


@pytest.fixture
def release(tmp_path):
    prepared = PreparedRelease(make_fixture(tmp_path/"TEST_FIXTURE_ONLY"))
    prepared.preflight()
    return prepared


@pytest.fixture
def mongo_case(release):
    if os.environ.get("HDBI_RUN_MONGO_TESTS") != "1":
        pytest.skip("Real MongoDB tests require HDBI_RUN_MONGO_TESTS=1 and HDBI_TEST_MONGODB_URI")
    uri = os.environ.get("HDBI_TEST_MONGODB_URI")
    if not uri:
        pytest.fail("Explicit HDBI_TEST_MONGODB_URI is required; no inferred server is used")
    from pymongo import MongoClient
    from hdb_insights.db.mongo_connection import database
    from hdb_insights.db.mongo_contract import COLLECTIONS, CONTRACT_VERSION, SCHEMA_REVISION
    from hdb_insights.db.mongo_indexes import create_indexes
    from hdb_insights.db.mongo_schema import ensure_collection
    from hdb_insights.db.mongodb_adapter import MongoDBAdapter, proposed_options_formatter
    client = MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=15000, retryWrites=False)
    client.admin.command("ping")
    db = database(client, "hdb_insights_demo")
    prefix = "_test_"+uuid.uuid4().hex+"_"
    names = {name: prefix+name for name in (*COLLECTIONS, "application_metadata", "demo_resale_transactions")}
    assert not set(names.values()) & set(db.list_collection_names())
    try:
        for kind, name in names.items():
            ensure_collection(db, name, kind)
            create_indexes(db[name], kind)
        for kind in COLLECTIONS:
            docs = [{"_id": row["record_id"], **row} for row in release.typed_rows("D01")] if kind == "resale_transactions" else release.documents[kind]
            if docs:
                db[names[kind]].insert_many(docs)
        metadata = {"_id": "active", "contract_version": CONTRACT_VERSION, "data_release_id": release.manifest["data_release_id"],
            "schema_revision": SCHEMA_REVISION, "snapshot_id": release.manifest["snapshot_id"], "manifest_sha256": release.manifest_hash,
            "publication_id": prefix, "loaded_at_utc": "2026-10-24T00:00:00+00:00", "content_digests": release.fact_digests,
            "collection_digests": release.collection_digests}
        db[names["application_metadata"]].insert_one(metadata)
        adapter = MongoDBAdapter(client, "hdb_insights_demo", options_formatter=proposed_options_formatter, _test_prefix=prefix)
        yield {"client": client, "db": db, "prefix": prefix, "names": names, "release": release, "adapter": adapter, "uri": uri}
    finally:
        # Drop only randomly named collections created and owned by THIS fixture.
        for name in names.values():
            db.drop_collection(name)
        client.close()
