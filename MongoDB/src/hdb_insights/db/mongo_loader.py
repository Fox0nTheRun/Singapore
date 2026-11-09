"""Staged, content-checked imports and journalled OFFLINE publication.

Collection renames are deliberately not described as an atomic release switch.
Stop and drain the application before publishing or recovering a release.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util
from pymongo.errors import DuplicateKeyError
from .mongo_contract import COLLECTIONS, CONTRACT_VERSION, SCHEMA_REVISION, InputError
from .mongo_indexes import check_indexes, create_indexes
from .mongo_prepared import document_digests, verify_loaded
from .mongo_schema import VALIDATORS, ensure_collection

LOCK_COLLECTION = "_mongo_loader_lock"


def write_journal(path, state):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json_util.dumps(state, indent=2))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if hasattr(os, "O_DIRECTORY"):
        descriptor = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def collection_uuid(db, name):
    infos = list(db.list_collections(filter={"name": name}))
    return infos[0]["info"]["uuid"] if infos else None


def verify_schema_and_indexes(db, names):
    for kind, name in names.items():
        if collection_uuid(db, name) is None:
            raise InputError(f"{name}: required collection is absent")
        options = db[name].options()
        if options.get("validator") != VALIDATORS[kind]() or options.get("validationLevel", "strict") != "strict" or options.get("validationAction", "error") != "error":
            raise InputError(f"{name}: installed validator differs")
        if db[name].count_documents({"$nor": [VALIDATORS[kind]()]}, limit=1):
            raise InputError(f"{name}: stored document violates its validator")
        check_indexes(db[name], kind)


def insert_batches(collection, rows, batch_size=500):
    pending = []
    for row in rows:
        pending.append(row)
        if len(pending) >= batch_size:
            result = collection.insert_many(pending, ordered=True)
            if not result.acknowledged:
                raise InputError("An import write was not acknowledged")
            pending.clear()
    if pending:
        result = collection.insert_many(pending, ordered=True)
        if not result.acknowledged:
            raise InputError("An import write was not acknowledged")


def stage_release(release, db, run_id):
    if not release.validated:
        raise InputError("Preflight is required before staging")
    if release.is_fixture and db.name != "hdb_insights_demo":
        raise InputError("Fixture staging is restricted to the isolated hdb_insights_demo database")
    names = {name: f"_c_{run_id}_{name}" for name in COLLECTIONS}
    if any(collection_uuid(db, name) is not None for name in names.values()):
        raise InputError("Candidate names already exist")
    for kind, name in names.items():
        ensure_collection(db, name, kind)
        create_indexes(db[name], kind)
        if kind == "resale_transactions":
            rows = ({"_id": row["record_id"], **row} for row in release.typed_rows("D01"))
        else:
            rows = iter(release.documents[kind])
        insert_batches(db[name], rows)
    release.check_unchanged()
    verify_schema_and_indexes(db, names)
    verify_loaded(release, db, names)
    return names


def acquire_lock(db, run_id):
    try:
        db[LOCK_COLLECTION].insert_one({"_id": "exclusive", "run_id": run_id})
    except DuplicateKeyError:
        raise InputError("Another loader/recovery lock exists; inspect its journal before proceeding") from None


def release_lock(db, run_id):
    db[LOCK_COLLECTION].delete_one({"_id": "exclusive", "run_id": run_id})


def publish_release(release, db, names, journal_path, run_id, *, maintenance_confirmed=False):
    if not maintenance_confirmed:
        raise InputError("Publication requires an acknowledged offline maintenance window")
    if release.is_fixture:
        raise InputError("Labelled test fixtures cannot be published as analytical source data")
    canonical = {name: name for name in COLLECTIONS}
    ensure_collection(db, "application_metadata", "application_metadata")
    old_metadata = db.application_metadata.find_one({"_id": "active"})
    if db.application_metadata.count_documents({}) != (1 if old_metadata else 0):
        raise InputError("Unexpected application metadata documents")
    if old_metadata:
        verify_schema_and_indexes(db, {**canonical, "application_metadata": "application_metadata"})
        if document_digests(db, canonical) != old_metadata.get("collection_digests"):
            raise InputError("Prior analytical release has drifted; publication refused")
    else:
        for name in COLLECTIONS:
            if collection_uuid(db, name) is not None:
                verify_schema_and_indexes(db, {name: name})
                if db[name].count_documents({}, limit=1):
                    raise InputError("Unknown populated target without active metadata; publication refused")
    state = {"journal_version": 1, "database_name": db.name, "run_id": run_id,
        "phase": "prepared", "old_metadata": old_metadata, "new_release": release.manifest["data_release_id"],
        "candidate_names": names, "candidate_uuids": {kind: collection_uuid(db, name) for kind, name in names.items()},
        "backup_names": {name: f"_b_{run_id}_{name}" for name in COLLECTIONS},
        "old_uuids": {name: collection_uuid(db, name) for name in COLLECTIONS},
        "metadata_backup": f"_b_{run_id}_application_metadata"}
    if any(collection_uuid(db, name) is not None for name in [*state["backup_names"].values(), state["metadata_backup"]]):
        raise InputError("Backup names already exist")
    # Persist rename intentions before touching any live data.
    write_journal(journal_path, state)
    if old_metadata:
        ensure_collection(db, state["metadata_backup"], "application_metadata")
        db[state["metadata_backup"]].insert_one(old_metadata)
    state["phase"] = "switching"
    write_journal(journal_path, state)
    db.application_metadata.delete_one({"_id": "active"})
    for name in COLLECTIONS:
        if state["old_uuids"][name] is not None:
            db[name].rename(state["backup_names"][name], dropTarget=False)
        db[names[name]].rename(name, dropTarget=False)
        state["last_completed"] = name
        write_journal(journal_path, state)
    verify_schema_and_indexes(db, canonical)
    verify_loaded(release, db, canonical)
    release.check_unchanged()
    metadata = {"_id": "active", "contract_version": CONTRACT_VERSION,
        "data_release_id": release.manifest["data_release_id"], "schema_revision": SCHEMA_REVISION,
        "snapshot_id": release.manifest["snapshot_id"], "manifest_sha256": release.manifest_hash,
        "publication_id": run_id, "loaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "content_digests": release.fact_digests, "collection_digests": release.collection_digests}
    db.application_metadata.insert_one(metadata)  # Metadata LAST.
    state["phase"] = "committed"
    write_journal(journal_path, state)
    return state


def rollback_publication(db, journal_path, *, maintenance_confirmed=False):
    """Restart-safe rollback using actual UUIDs, including ambiguous rename outcomes."""
    if not maintenance_confirmed:
        raise InputError("Recovery requires a paused, drained application")
    state = json_util.loads(Path(journal_path).read_text(encoding="utf-8"))
    if state["database_name"] != db.name or state.get("journal_version") != 1:
        raise InputError("Recovery journal belongs to another database/version")
    run_id = state["run_id"]
    lock = db[LOCK_COLLECTION].find_one({"_id": "exclusive"})
    if lock is None:
        acquire_lock(db, run_id)
    elif lock.get("run_id") != run_id:
        raise InputError("Another maintenance operation owns the lock")
    if state["phase"] in ("staging", "staging_failed", "staged", "staging_abandoned"):
        # No cutover intentions existed: leave the active release and candidates
        # alone, and release only this operation's crash-surviving lock.
        state["phase"] = "staging_abandoned"
        write_journal(journal_path, state)
        release_lock(db, run_id)
        return state
    old = state["old_metadata"]
    active = db.application_metadata.find_one({"_id": "active"})
    if active is not None and active != old and active.get("publication_id") != run_id:
        raise InputError("Active metadata was changed by an unknown operation")
    state["phase"] = "rolling_back"
    write_journal(journal_path, state)
    db.application_metadata.delete_one({"_id": "active"})
    for name in COLLECTIONS:
        old_uuid = state["old_uuids"][name]
        candidate_uuid = state["candidate_uuids"][name]
        backup = state["backup_names"][name]
        staged = state["candidate_names"][name]
        current_uuid = collection_uuid(db, name)
        if current_uuid == candidate_uuid:
            if collection_uuid(db, staged) is not None:
                raise InputError("Recovery candidate target is unexpectedly occupied")
            db[name].rename(staged, dropTarget=False)
            current_uuid = None
        if old_uuid is not None:
            backup_uuid = collection_uuid(db, backup)
            if current_uuid == old_uuid and backup_uuid is None:
                continue  # Original rename never happened.
            if current_uuid is not None or backup_uuid != old_uuid:
                raise InputError("Cannot safely identify the prior canonical collection")
            db[backup].rename(name, dropTarget=False)
        elif current_uuid is not None:
            raise InputError("Recovery found an unknown canonical collection")
    if old:
        canonical = {name: name for name in COLLECTIONS}
        verify_schema_and_indexes(db, canonical)
        if document_digests(db, canonical) != old["collection_digests"]:
            raise InputError("Restored prior release did not pass full content verification")
        db.application_metadata.insert_one(old)
    else:
        for name in COLLECTIONS:
            if collection_uuid(db, name) is not None and db[name].count_documents({}, limit=1):
                raise InputError("Unexpected populated collection after initial-load rollback")
    state["phase"] = "rolled_back"
    write_journal(journal_path, state)
    release_lock(db, run_id)
    return state


def load_release(release, db, journal_path, *, publish=False, maintenance_confirmed=False):
    if not release.validated:
        release.preflight()
    if publish and (not maintenance_confirmed or release.is_fixture):
        raise InputError("Publication needs maintenance acknowledgement and real prepared inputs")
    if Path(journal_path).exists():
        raise InputError("Journal already exists; use a new path or recover the existing operation")
    run_id = uuid.uuid4().hex[:12]
    acquire_lock(db, run_id)
    try:
        active = db.application_metadata.find_one({"_id": "active"})
        if active and active.get("data_release_id") == release.manifest["data_release_id"]:
            if active.get("snapshot_id") != release.manifest["snapshot_id"] or active.get("content_digests") != release.fact_digests or active.get("collection_digests") != release.collection_digests:
                raise InputError("Same-ID content drift or short-ID collision")
            canonical = {name: name for name in COLLECTIONS}
            verify_schema_and_indexes(db, {**canonical, "application_metadata": "application_metadata"})
            verify_loaded(release, db, canonical)
            release.check_unchanged()
            return {"status": "VERIFIED_NO_OP", "data_release_id": active["data_release_id"]}
        write_journal(journal_path, {"journal_version": 1, "database_name": db.name,
            "run_id": run_id, "phase": "staging", "candidate_names": {name: f"_c_{run_id}_{name}" for name in COLLECTIONS}})
        names = stage_release(release, db, run_id)
        if not publish:
            write_journal(journal_path, {"journal_version": 1, "database_name": db.name,
                "run_id": run_id, "phase": "staged", "candidate_names": names})
            return {"status": "STAGED_ONLY", "candidate_names": names, "data_release_id": None,
                    "note": "Canonical analytics and active metadata were not changed"}
        publish_release(release, db, names, journal_path, run_id, maintenance_confirmed=maintenance_confirmed)
        return {"status": "PUBLISHED", "data_release_id": release.manifest["data_release_id"], "journal_path": str(journal_path)}
    except Exception as exc:
        if Path(journal_path).exists():
            state = json_util.loads(Path(journal_path).read_text())
            if state["phase"] == "staging":
                state.update(phase="staging_failed", error_class=type(exc).__name__)
                write_journal(journal_path, state)
        raise
    finally:
        # Keep a crash/failure lock during cutover until explicit recovery succeeds.
        state = json_util.loads(Path(journal_path).read_text()) if Path(journal_path).exists() else None
        if state is None or state["phase"] in ("staging", "staging_failed", "staged", "prepared", "committed", "rolled_back"):
            release_lock(db, run_id)
