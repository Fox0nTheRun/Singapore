"""Journal state-machine tests with a tiny fake store, NOT MongoDB acceptance.

These verify sequencing and UUID safety under injected interruption positions.
Real rename/validation/permissions/crash acceptance still needs MongoDB.
"""
from copy import deepcopy
import pytest
from hdb_insights.db.mongo_contract import COLLECTIONS, InputError
from hdb_insights.db.mongo_loader import LOCK_COLLECTION, rollback_publication, write_journal
import hdb_insights.db.mongo_loader as loader


class Store:
    name = "hdb_insights_demo"
    def __init__(self):
        self.items = {}
    def __getitem__(self, name):
        return Collection(self, name)
    @property
    def application_metadata(self):
        return self["application_metadata"]
    def list_collections(self, filter):
        row = self.items.get(filter["name"])
        return [{"info": {"uuid": row["uuid"]}}] if row else []


class Collection:
    def __init__(self, store, name):
        self.store, self.name = store, name
    def find_one(self, query):
        for doc in self.store.items.get(self.name, {}).get("documents", []):
            if all(doc.get(k) == v for k, v in query.items()):
                return deepcopy(doc)
        return None
    def insert_one(self, doc):
        if self.name == "application_metadata":
            assert all(self.store.items.get(name, {}).get("uuid") == "old:"+name for name in COLLECTIONS), "Metadata restored before the complete prior release"
        row = self.store.items.setdefault(self.name, {"uuid": self.name, "documents": []})
        assert not any(old["_id"] == doc["_id"] for old in row["documents"])
        row["documents"].append(deepcopy(doc))
    def delete_one(self, query):
        row = self.store.items.get(self.name)
        if row:
            row["documents"] = [doc for doc in row["documents"] if not all(doc.get(k) == v for k, v in query.items())]
    def rename(self, target, dropTarget=False):
        assert not dropTarget
        assert target not in self.store.items
        assert self.name in self.store.items
        assert not self.store.application_metadata.find_one({"_id": "active"}), "Reader readiness remained active during a rename"
        self.store.items[target] = self.store.items.pop(self.name)
    def count_documents(self, query, limit=None):
        return len(self.store.items.get(self.name, {}).get("documents", []))


@pytest.mark.parametrize("completed_renames", range(9))
def test_T_C_07_algorithm_recovers_each_interruption(tmp_path, monkeypatch, completed_renames):
    db = Store()
    run = "algorithm_test"
    state = {"journal_version": 1, "database_name": db.name, "run_id": run, "phase": "switching",
        "candidate_names": {name: "candidate:"+name for name in COLLECTIONS},
        "backup_names": {name: "backup:"+name for name in COLLECTIONS},
        "old_uuids": {name: "old:"+name for name in COLLECTIONS},
        "candidate_uuids": {name: "new:"+name for name in COLLECTIONS},
        "old_metadata": {"_id": "active", "publication_id": "prior", "collection_digests": {"test": "old_digests"}}}
    for name in COLLECTIONS:
        db.items[name] = {"uuid": "old:"+name, "documents": [{"_id": "fixture_old"}]}
        db.items["candidate:"+name] = {"uuid": "new:"+name, "documents": [{"_id": "fixture_new"}]}
    operations = [pair for name in COLLECTIONS for pair in ((name, "backup:"+name), ("candidate:"+name, name))]
    for source, target in operations[:completed_renames]:
        db[source].rename(target)
    def checked_old(store, names):
        assert all(store.items[name]["uuid"] == "old:"+kind for kind, name in names.items())
    monkeypatch.setattr(loader, "verify_schema_and_indexes", checked_old)
    monkeypatch.setattr(loader, "document_digests", lambda store, names: {"test": "old_digests"})
    journal = tmp_path/"recovery.json"
    write_journal(journal, state)
    result = rollback_publication(db, journal, maintenance_confirmed=True)
    assert result["phase"] == "rolled_back"
    assert db.application_metadata.find_one({"_id": "active"}) == state["old_metadata"]
    assert db[LOCK_COLLECTION].find_one({"_id": "exclusive"}) is None
    assert all(db.items[name]["uuid"] == "old:"+name for name in COLLECTIONS)


def test_staging_crash_does_not_touch_active_release(tmp_path):
    db = Store()
    db.items["application_metadata"] = {"uuid": "meta", "documents": [{"_id": "active", "publication_id": "prior"}]}
    before = deepcopy(db.items["application_metadata"])
    journal = tmp_path/"staging.json"
    write_journal(journal, {"journal_version": 1, "database_name": db.name, "run_id": "staging_test", "phase": "staging"})
    assert rollback_publication(db, journal, maintenance_confirmed=True)["phase"] == "staging_abandoned"
    assert db.items["application_metadata"] == before


def test_unknown_uuid_blocks_recovery_before_overwrite(tmp_path):
    db = Store()
    first = COLLECTIONS[0]
    db.items[first] = {"uuid": "UNKNOWN", "documents": [{"_id": "not_owned"}]}
    state = {"journal_version": 1, "database_name": db.name, "run_id": "unknown_test", "phase": "switching", "old_metadata": None,
        "old_uuids": {name: "old:"+name for name in COLLECTIONS}, "candidate_uuids": {name: "new:"+name for name in COLLECTIONS},
        "candidate_names": {name: "candidate:"+name for name in COLLECTIONS}, "backup_names": {name: "backup:"+name for name in COLLECTIONS}}
    journal = tmp_path/"unknown.json"
    write_journal(journal, state)
    with pytest.raises(InputError, match="safely identify"):
        rollback_publication(db, journal, maintenance_confirmed=True)
    assert db.items[first]["uuid"] == "UNKNOWN"
    assert db.application_metadata.find_one({"_id": "active"}) is None
