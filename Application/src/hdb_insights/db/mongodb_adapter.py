"""C05 synchronous MongoDB adapter, ready for D's lifecycle integration.

The two unresolved wire-shape choices stay explicit constructor dependencies.
They do not prevent resale, demographic, valid mobility or CRUD development.
"""
from __future__ import annotations

import logging
import inspect
import re
import uuid
from dataclasses import dataclass
from functools import wraps

from pymongo import ReturnDocument
from pymongo.errors import ConnectionFailure, DuplicateKeyError, OperationFailure, PyMongoError
from .mongo_connection import connect, database
from .mongo_contract import (CONTRACT_VERSION, EDITABLE_FIELDS, ETHNIC_CODES, MODES, REGIONS,
    RESALE_FIELDS, RESALE_FLATS, InputError, ServiceError, code, integer, json_safe,
    resale_business, resale_filter, text)
from .mongo_queries import mobility_pipeline, resale_summary_pipeline
from .mongo_schema import demo_validator

LOGGER = logging.getLogger(__name__)


@dataclass
class Reply:
    data: object
    note: str | None = None


def response(*, demo=False):
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            meta = {"backend": "mongodb", "contract_version": None, "data_release_id": None}
            if demo:
                meta.update(dataset_kind="demo", base_data_release_id=None)
            result = None
            try:
                active = self._active()
                meta.update(contract_version=active["contract_version"], data_release_id=active["data_release_id"])
                if demo:
                    meta["base_data_release_id"] = active["data_release_id"]
                result = method(self, active, *args, **kwargs)
                after = self._active()
                if after["publication_id"] != active["publication_id"]:
                    raise ServiceError("DATA_NOT_READY", "The analytical release changed; retry after maintenance")
                if isinstance(result, Reply):
                    if result.note:
                        meta["note"] = result.note
                    result = result.data
                return {"ok": True, "data": json_safe(result), "error": None, "meta": meta}
            except InputError as exc:
                error = {"code": "VALIDATION_ERROR", "message": str(exc)}
            except ServiceError as exc:
                error = {"code": exc.code, "message": str(exc)}
            except DuplicateKeyError:
                error = {"code": "CONFLICT", "message": "A record with this identity already exists"}
            except ConnectionFailure:
                error = {"code": "DB_UNAVAILABLE", "message": "MongoDB is unavailable; check the connection"}
            except OperationFailure as exc:
                LOGGER.warning("MongoDB operation failed: %s, code=%s", type(exc).__name__, exc.code)
                error = {"code": "VALIDATION_ERROR" if exc.code == 121 else "DB_UNAVAILABLE" if exc.code in (13, 18, 50) else "INTERNAL_ERROR", "message": "MongoDB rejected the operation; check configuration and validated inputs"}
            except PyMongoError as exc:
                LOGGER.warning("MongoDB driver failure: %s", type(exc).__name__)
                error = {"code": "DB_UNAVAILABLE", "message": "MongoDB could not complete the operation"}
            except Exception as exc:
                # Do not log raw driver exceptions, credentials or arbitrary payloads.
                LOGGER.error("MongoDB adapter defect: %s", type(exc).__name__)
                error = {"code": "INTERNAL_ERROR", "message": "An internal database error occurred"}
            if demo and method.__name__ == "create_demo_resale" and isinstance(result, dict) and result.get("demo_record_id"):
                error["message"] += "; check "+result["demo_record_id"]+" before retrying create"
            return {"ok": False, "data": None, "error": error, "meta": meta}
        signature = inspect.signature(method)
        wrapped.__signature__ = signature.replace(parameters=[p for p in signature.parameters.values() if p.name != "active"])
        return wrapped
    return decorate


class MongoDBAdapter:
    def __init__(self, client=None, database_name=None, *, options_formatter=None,
                 missing_mobility_policy=None, _test_prefix=None):
        self._owns_client = client is None
        self.client = client if client is not None else connect()
        self.db = database(self.client, database_name)
        self.demo_db = database(self.client, "hdb_insights_demo")
        if _test_prefix is not None and (self.db.name != "hdb_insights_demo" or not re.fullmatch(r"_test_[0-9a-f]+_", _test_prefix)):
            raise InputError("Private fixture prefix is allowed only in hdb_insights_demo")
        self.prefix = _test_prefix or ""
        self.options_formatter = options_formatter
        if missing_mobility_policy not in (None, "NOT_FOUND", "EMPTY"):
            raise InputError("Unsupported coordinated missing-mobility policy")
        self.missing_mobility_policy = missing_mobility_policy

    def collection(self, kind):
        return self.db[self.prefix+kind]

    @property
    def demo(self):
        return self.demo_db[self.prefix+"demo_resale_transactions"]

    def close(self):
        if self._owns_client:
            self.client.close()

    def _active(self):
        active = self.collection("application_metadata").find_one({"_id": "active"})
        if not active or active.get("contract_version") != CONTRACT_VERSION or not all(isinstance(active.get(key), str) and active[key] for key in ("data_release_id", "publication_id", "snapshot_id")):
            raise ServiceError("DATA_NOT_READY", "A complete compatible analytical release is not active")
        return active

    def _match(self, filters):
        predicate = resale_filter(filters)
        if "town_name" in predicate and not self.collection("resale_transactions").find_one({"town_name": predicate["town_name"]}, {"_id": 1}):
            raise InputError("Unknown town_name")
        return predicate

    @response()
    def list_filter_options(self, active, domain):
        code(domain, ("resale", "demographic", "mobility"), "domain")
        if domain == "resale":
            coll = self.collection("resale_transactions")
            internal = {field: sorted(coll.distinct(field)) for field in ("town_name", "flat_type_code", "registration_month")}
        elif domain == "demographic":
            internal = {"profiles": list(self.collection("demographic_profiles").find({}, {"_id": 0, "group_type": 1, "group_code": 1, "survey_year": 1}).sort([("group_type", 1), ("group_code", 1), ("survey_year", 1)]))}
        else:
            coll = self.collection("mobility_profiles")
            internal = {"workplaces": list(coll.find({}, {"_id": 0, "survey_year": 1, "workplace_area": 1, "workplace_area_kind": 1}).sort([("survey_year", 1), ("workplace_area", 1)])),
                        "residence_region_code": sorted(coll.distinct("observations.residence_region_code"))}
        if self.options_formatter is None:
            raise ServiceError("DATA_NOT_READY", "The filter-options wire shape needs D/B/E agreement; supply the agreed options_formatter")
        options = self.options_formatter(domain, internal)
        if not isinstance(options, dict):
            raise RuntimeError("options_formatter must return a dict")
        return {"options": options}

    @response()
    def search_resale(self, active, filters, limit=50, offset=0):
        limit = integer(limit, "limit", 1, 500)
        offset = integer(offset, "offset", 0, 2**63-1)
        predicate = self._match(filters)
        coll = self.collection("resale_transactions")
        total = coll.count_documents(predicate)
        cursor = coll.find(predicate, {"_id": 0, **{key: 1 for key in RESALE_FIELDS}}).sort([("registration_month", 1), ("record_id", 1)]).skip(offset).limit(limit)
        return {"rows": list(cursor), "total_count": total, "limit": limit, "offset": offset}

    @response()
    def summarise_resale(self, active, filters):
        rows = list(self.collection("resale_transactions").aggregate(resale_summary_pipeline(self._match(filters))))
        return rows[0] if rows else {"transaction_count": 0, "average_price": None, "average_price_per_sqm": None}

    @response()
    def resale_trend(self, active, filters):
        return {"rows": list(self.collection("resale_transactions").aggregate(resale_summary_pipeline(self._match(filters), trend=True)))}

    @response()
    def demographic_profile(self, active, group_type, group_code, survey_year):
        code(group_type, ("flat_type", "ethnicity"), "group_type")
        code(group_code, (*RESALE_FLATS, "ALL") if group_type == "flat_type" else (*ETHNIC_CODES, "ALL"), "group_code")
        year = integer(survey_year, "survey_year", 1, 9999)
        profile = self.collection("demographic_profiles").find_one({"group_type": group_type, "group_code": group_code, "survey_year": year}, {"_id": 0})
        if profile is None:
            return Reply(None, "This category/year has no published demographic profile")
        return profile

    @response()
    def mobility_breakdown(self, active, workplace_area, residence_region_code, survey_year=2020):
        area = text(workplace_area, "workplace_area")
        region = code(residence_region_code, REGIONS, "residence_region_code")
        year = integer(survey_year, "survey_year", 1, 9999)
        rows = list(self.collection("mobility_profiles").aggregate(mobility_pipeline(area, region, year)))
        if not rows:
            if self.missing_mobility_policy == "NOT_FOUND":
                raise ServiceError("NOT_FOUND", "No published mobility profile for this area/year")
            if self.missing_mobility_policy == "EMPTY":
                return {"rows": [], "published_total": None, "note": "No published mobility profile for this area/year"}
            raise ServiceError("DATA_NOT_READY", "D/B/E must agree the missing mobility area/year response")
        if len(rows) != 4:
            raise ServiceError("DATA_NOT_READY", "The mobility profile is incomplete")
        total = rows[0]["published_total"]
        return {"rows": [{key: row[key] for key in ("transport_mode_code", "count", "count_status", "share_pct")} for row in rows],
            "published_total": total,
            "note": "Residence region; employed residents aged 15+. Shares use the published total. Dashes are unresolved nulls; published components may differ from totals through rounding. Shares are not normalised."}

    def _demo_ready(self):
        # Setup is an admin job; app credentials do not create/modify validators.
        options = self.demo.options()
        if options.get("validator") != demo_validator() or options.get("validationLevel", "strict") != "strict" or options.get("validationAction", "error") != "error":
            raise ServiceError("DATA_NOT_READY", "Run the explicit demo-schema setup before CRUD")

    @staticmethod
    def _demo_id(value):
        if not isinstance(value, str) or not value.startswith("demo:"):
            raise InputError("Expected a demo:<UUID> identity")
        try:
            if str(uuid.UUID(value[5:])) != value[5:]:
                raise ValueError()
        except ValueError:
            raise InputError("Expected a demo:<UUID> identity") from None
        return value

    def _demo_record(self, active, identity):
        identity = self._demo_id(identity)
        self._demo_ready()
        row = self.demo.find_one({"_id": identity})
        if row is None:
            raise ServiceError("NOT_FOUND", "Demo record was not found")
        if row.get("base_data_release_id") != active["data_release_id"]:
            raise ServiceError("DATA_NOT_READY", "Demo seed belongs to a different release; controlled reset/reseed is required")
        return row

    @staticmethod
    def _public_demo(row):
        return {key: value for key, value in row.items() if key not in ("_id", "seed_lineage", "revision")}

    def _conflict_or_missing(self, identity):
        if not self.demo.find_one({"_id": identity}, {"_id": 1}):
            raise ServiceError("NOT_FOUND", "Demo record was deleted concurrently")
        raise ServiceError("CONFLICT", "Demo record changed concurrently; reload before retrying")

    @response(demo=True)
    def create_demo_resale(self, active, payload):
        if not isinstance(payload, dict) or set(payload) != {"seed_record_id", *EDITABLE_FIELDS}:
            raise InputError("Create requires seed_record_id and exactly the editable resale business fields")
        seed_id = text(payload["seed_record_id"], "seed_record_id")
        business = resale_business({key: payload[key] for key in EDITABLE_FIELDS})
        seed = self.collection("resale_transactions").find_one({"_id": seed_id})
        if seed is None:
            raise ServiceError("NOT_FOUND", "The real analytical seed record was not found")
        self._demo_ready()
        identity = "demo:"+str(uuid.uuid4())
        row = {"_id": identity, "demo_record_id": identity, "record_kind": "demo", "seed_record_id": seed_id,
            "base_data_release_id": active["data_release_id"], **business,
            "seed_lineage": {key: seed[key] for key in ("dataset_id", "source_file_sha256", "source_row_number")}, "revision": 0}
        try:
            result = self.demo.insert_one(row)
        except ConnectionFailure:
            raise ServiceError("DB_UNAVAILABLE", f"Write acknowledgement was lost; check {identity} before retrying create") from None
        if not result.acknowledged:
            raise ServiceError("DB_UNAVAILABLE", f"Write was not acknowledged; check {identity} before retrying create")
        try:
            return self._public_demo(self._demo_record(active, identity))
        except PyMongoError:
            raise ServiceError("DB_UNAVAILABLE", f"Created record could not be read back; check {identity} before retrying create") from None

    @response(demo=True)
    def get_demo_resale(self, active, demo_record_id):
        return self._public_demo(self._demo_record(active, demo_record_id))

    @response(demo=True)
    def update_demo_resale(self, active, demo_record_id, changes):
        if not isinstance(changes, dict) or not changes or set(changes) - set(EDITABLE_FIELDS):
            raise InputError("Update needs nonempty editable business fields; identity/lineage/operators cannot change")
        original = self._demo_record(active, demo_record_id)
        business = resale_business({**{key: original[key] for key in EDITABLE_FIELDS}, **changes})
        updated = self.demo.find_one_and_update({"_id": original["_id"], "revision": original["revision"], "base_data_release_id": active["data_release_id"]},
            {"$set": business, "$inc": {"revision": 1}}, return_document=ReturnDocument.AFTER)
        if updated is None:
            self._conflict_or_missing(original["_id"])
        return self._public_demo(updated)

    @response(demo=True)
    def delete_demo_resale(self, active, demo_record_id):
        original = self._demo_record(active, demo_record_id)
        result = self.demo.delete_one({"_id": original["_id"], "revision": original["revision"], "base_data_release_id": active["data_release_id"]})
        if not result.acknowledged:
            raise ServiceError("DB_UNAVAILABLE", "Delete was not acknowledged; read the record before retrying")
        if result.deleted_count != 1:
            self._conflict_or_missing(original["_id"])
        return {"deleted_count": 1}


def proposed_options_formatter(domain, db_options):
    """Local demonstration ONLY: forward DB-backed keys pending D/B/E review."""
    return db_options
