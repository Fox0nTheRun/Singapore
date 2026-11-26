"""Strict MongoDB validators; cross-collection provenance is loader enforced."""
from __future__ import annotations

from copy import deepcopy
from bson.decimal128 import Decimal128
from .mongo_contract import (AGE_CODES, COLUMN_MAP, CONTRACT_VERSION, DATASET_IDS,
    EDITABLE_FIELDS, ETHNIC_CODES, FLAT_CODES, MODES, REGIONS, RESALE_FLATS,
    SCHEMA_REVISION, SPECIAL_AREAS, InputError)


def obj(properties: dict, *, required=None) -> dict:
    return {"bsonType": "object", "required": list(properties if required is None else required),
            "additionalProperties": False, "properties": properties}


def string(*, enum=None, pattern=None) -> dict:
    out = {"bsonType": "string", "minLength": 1}
    if enum is not None:
        out["enum"] = list(enum)
    if pattern is not None:
        out["pattern"] = pattern
    return out


def integer(minimum=0, maximum=2**31 - 1, *, long=False) -> dict:
    return {"bsonType": "long" if long else "int", "minimum": minimum, "maximum": maximum}


def dec(precision=5, *, positive=False) -> dict:
    return {"bsonType": "decimal", "minimum": Decimal128("0"),
            "exclusiveMinimum": positive,
            "maximum": Decimal128(str(10**(precision - 2) - 1) + ".99")}


def array(items, minimum, maximum) -> dict:
    return {"bsonType": "array", "items": items, "minItems": minimum, "maxItems": maximum}


SHA = string(pattern="^[0-9a-f]{64}$")
ROW = {"bsonType": ["int", "long"], "minimum": 1}
PROVENANCE = {"dataset_id": string(enum=DATASET_IDS), "source_file_sha256": SHA, "source_row_number": ROW}
RECORD_PATTERN = "^D01:[0-9a-f]{64}:[0-9]{9}$"
MONTH_PATTERN = "^(?!0000)[0-9]{4}-(0[1-9]|1[0-2])$"


def safe_string(path):
    return {"$convert": {"input": path, "to": "string", "onError": "", "onNull": ""}}


def safe_array(path):
    return {"$cond": [{"$isArray": path}, path, []]}


def decimal_rule(path, precision=5, *, positive=False):
    # $cond guards $trunc against malformed types. Bounds also exclude infinities/NaN.
    return {"$cond": [{"$eq": [{"$type": path}, "decimal"]}, {"$and": [
        {"$not": [{"$in": [safe_string(path), ["NaN", "Infinity", "-Infinity"]]}]},
        {"$gt" if positive else "$gte": [path, Decimal128("0")]},
        {"$lte": [path, Decimal128(str(10**(precision-2)-1) + ".99")]},
        {"$eq": [path, {"$trunc": [path, 2]}]},
    ]}, False]}


def validator(schema, *expressions):
    return {"$and": [{"$jsonSchema": schema}, {"$expr": {"$and": list(expressions)}}]} if expressions else {"$jsonSchema": schema}


def resale_properties():
    return {
        "registration_month": string(pattern=MONTH_PATTERN), "town_name": string(),
        "flat_type_code": string(enum=RESALE_FLATS), "block": string(), "street_name": string(),
        "storey_lower": integer(), "storey_upper": integer(), "floor_area_sqm": dec(8, positive=True),
        "flat_model": string(), "lease_commence_year": integer(1, 9999),
        "remaining_lease_months": integer(), "resale_price": dec(14, positive=True),
    }


def resale_rules():
    rules = [{"$lte": ["$storey_lower", "$storey_upper"]},
             decimal_rule("$floor_area_sqm", 8, positive=True), decimal_rule("$resale_price", 14, positive=True)]
    for field in ("town_name", "street_name", "block", "flat_model"):
        s = safe_string("$"+field)
        rules.append({"$eq": [s, {"$trim": {"input": s}}]})
        if field in ("town_name", "street_name"):
            rules.append({"$eq": [s, {"$toUpper": s}]})
    return rules


def source_validator():
    return validator(obj({"_id": string(enum=DATASET_IDS), "source_filename": string(),
        "source_file_sha256": SHA, "source_row_count": {"bsonType": ["int", "long"], "minimum": 0}}))


def resale_validator():
    props = {"_id": string(pattern=RECORD_PATTERN), "record_id": string(pattern=RECORD_PATTERN),
             **resale_properties(), **deepcopy(PROVENANCE)}
    props["dataset_id"] = string(enum=("D01",))
    return validator(obj(props), {"$eq": ["$_id", "$record_id"]}, *resale_rules())


def demographic_validator():
    pop = integer(0, 2**63-1, long=True)
    pop["bsonType"] = ["long", "null"]
    age_entry = obj({"age_group_code": string(enum=AGE_CODES), "percentage": {**dec(), "maximum": Decimal128("100")}})
    props = {"_id": string(), "group_type": string(enum=("flat_type", "ethnicity")),
        "group_code": string(enum=(*FLAT_CODES, *ETHNIC_CODES, "ALL")), "survey_year": integer(1, 9999),
        "average_age": dec(), "median_age": dec(), "population_15_plus": pop,
        "population_status": string(enum=("reported", "not_provided")),
        "age_distribution": array(age_entry, 3, 3),
        "source_rows": array(obj(deepcopy(PROVENANCE)), 4, 5)}
    ages = safe_array("$age_distribution")
    keys = {"$map": {"input": ages, "as": "a", "in": "$$a.age_group_code"}}
    return validator(obj(props),
        {"$eq": ["$_id", {"$concat": [safe_string("$group_type"), ":", safe_string("$group_code"), ":", safe_string("$survey_year")]}]},
        {"$cond": [{"$eq": ["$group_type", "flat_type"]}, {"$in": ["$group_code", [*FLAT_CODES, "ALL"]]}, {"$in": ["$group_code", [*ETHNIC_CODES, "ALL"]]}]},
        {"$cond": [{"$eq": ["$group_code", "ALL"]}, {"$and": [
            {"$eq": ["$population_15_plus", None]}, {"$eq": ["$population_status", "not_provided"]},
            {"$eq": [{"$size": safe_array("$source_rows")}, 4]}]}, {"$and": [
            {"$eq": [{"$type": "$population_15_plus"}, "long"]}, {"$gte": ["$population_15_plus", 0]},
            {"$eq": ["$population_status", "reported"]}, {"$eq": [{"$size": safe_array("$source_rows")}, 5]}]}]},
        {"$eq": [{"$size": ages}, 3]}, {"$setEquals": [keys, list(AGE_CODES)]},
        decimal_rule("$average_age"), decimal_rule("$median_age"),
        {"$allElementsTrue": [{"$map": {"input": ages, "as": "a", "in": {"$and": [decimal_rule("$$a.percentage"), {"$lte": ["$$a.percentage", Decimal128("100")]}]}}}]})


def mobility_validator():
    count = integer(0, 2**63-1, long=True)
    count["bsonType"] = ["long", "null"]
    entry = obj({"residence_region_code": string(enum=REGIONS), "transport_mode_code": string(enum=("ALL", *MODES)),
        "count": count, "count_status": string(enum=("reported", "unresolved_dash")),
        "source_column": string(enum=tuple(COLUMN_MAP.values()))})
    props = {"_id": string(), "survey_year": integer(1, 9999), "workplace_area": string(),
        "workplace_area_kind": string(enum=("total", "special", "planning_area")),
        "observations": array(entry, 30, 30), **deepcopy(PROVENANCE)}
    props["dataset_id"] = string(enum=("D08",))
    observations = safe_array("$observations")
    key = {"$concat": [safe_string("$$o.residence_region_code"), ":", safe_string("$$o.transport_mode_code")]}
    expected = [region+":"+mode for region, mode in COLUMN_MAP]
    header = {"$switch": {"branches": [{"case": {"$eq": [key, region+":"+mode]}, "then": column} for (region, mode), column in COLUMN_MAP.items()], "default": ""}}
    return validator(obj(props),
        {"$eq": ["$_id", {"$concat": [safe_string("$survey_year"), ":", safe_string("$workplace_area")]}]},
        {"$eq": ["$workplace_area_kind", {"$cond": [{"$eq": ["$workplace_area", "Total"]}, "total", {"$cond": [{"$in": ["$workplace_area", list(SPECIAL_AREAS)]}, "special", "planning_area"]}]}]},
        {"$eq": [{"$size": observations}, 30]},
        {"$setEquals": [{"$map": {"input": observations, "as": "o", "in": key}}, expected]},
        {"$allElementsTrue": [{"$map": {"input": observations, "as": "o", "in": {"$and": [
            {"$eq": ["$$o.source_column", header]},
            {"$cond": [{"$eq": ["$$o.count_status", "reported"]}, {"$and": [{"$eq": [{"$type": "$$o.count"}, "long"]}, {"$gte": ["$$o.count", 0]}]}, {"$and": [{"$eq": ["$$o.count_status", "unresolved_dash"]}, {"$eq": ["$$o.count", None]}]}]},
        ]}}}]})


def metadata_validator():
    digest = obj({"count": {"bsonType": ["int", "long"], "minimum": 0}, "sha256": SHA})
    return validator(obj({"_id": string(enum=("active",)), "contract_version": string(enum=(CONTRACT_VERSION,)),
        "data_release_id": string(pattern="^[0-9a-f]{12}_c1\\.0\\.0_t[0-9]+\\.[0-9]+\\.[0-9]+$"),
        "schema_revision": string(enum=(SCHEMA_REVISION,)), "snapshot_id": SHA, "manifest_sha256": SHA,
        "publication_id": string(), "loaded_at_utc": string(),
        "content_digests": obj({dataset: deepcopy(digest) for dataset in DATASET_IDS}),
        "collection_digests": obj({name: deepcopy(digest) for name in ("source_datasets", "resale_transactions", "demographic_profiles", "mobility_profiles")})}))


def demo_validator():
    uuid_pattern = "^demo:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    lineage = deepcopy(PROVENANCE)
    lineage["dataset_id"] = string(enum=("D01",))
    props = {"_id": string(pattern=uuid_pattern), "demo_record_id": string(pattern=uuid_pattern),
        "record_kind": string(enum=("demo",)), "seed_record_id": string(pattern=RECORD_PATTERN),
        "base_data_release_id": string(), **resale_properties(), "seed_lineage": obj(lineage), "revision": integer()}
    return validator(obj(props), {"$eq": ["$_id", "$demo_record_id"]}, *resale_rules())


VALIDATORS = {"source_datasets": source_validator, "resale_transactions": resale_validator,
    "demographic_profiles": demographic_validator, "mobility_profiles": mobility_validator,
    "application_metadata": metadata_validator, "demo_resale_transactions": demo_validator}


def ensure_collection(db, name: str, kind: str, *, apply_schema_update=False):
    """Inspect first; never silently migrate an existing collection."""
    intended = VALIDATORS[kind]()
    info = list(db.list_collections(filter={"name": name}))
    if not info:
        db.create_collection(name, validator=intended, validationLevel="strict", validationAction="error")
        return "created"
    options = info[0].get("options", {})
    if options.get("validator") == intended and options.get("validationLevel", "strict") == "strict" and options.get("validationAction", "error") == "error":
        return "unchanged"
    if not apply_schema_update:
        raise InputError(f"{name}: existing validator differs; inspect it before an explicit schema update")
    # collMod does not retroactively validate old documents. Check them first.
    if db[name].count_documents({"$nor": [intended]}, limit=1):
        raise InputError(f"{name}: existing documents fail the proposed validator; migration required")
    db.command({"collMod": name, "validator": intended, "validationLevel": "strict", "validationAction": "error"})
    return "updated_explicitly"
