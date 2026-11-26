"""Database-side explorer calculations. Never pre-round ratios or use $round."""
from bson.decimal128 import Decimal128
from .mongo_contract import MODES


def resale_summary_pipeline(predicate, *, trend=False):
    stages = [{"$match": predicate}, {"$group": {
        "_id": "$registration_month" if trend else None,
        "transaction_count": {"$sum": 1}, "average_price": {"$avg": "$resale_price"},
        "average_price_per_sqm": {"$avg": {"$divide": ["$resale_price", "$floor_area_sqm"]}},
    }}]
    stages.append({"$project": {"_id": 0, **({"registration_month": "$_id"} if trend else {}),
        "transaction_count": 1, "average_price": 1, "average_price_per_sqm": 1}})
    if trend:
        stages.append({"$sort": {"registration_month": 1}})
    return stages


def mobility_pipeline(area, region, year):
    selected = {"$filter": {"input": "$observations", "as": "o", "cond": {"$eq": ["$$o.residence_region_code", region]}}}
    denominator = {"$arrayElemAt": [{"$filter": {"input": "$selected", "as": "o", "cond": {"$eq": ["$$o.transport_mode_code", "ALL"]}}}, 0]}
    # $cond guards division: zero and missing denominators never reach $divide.
    share = {"$cond": [{"$and": [{"$eq": ["$selected.count_status", "reported"]},
        {"$eq": ["$denominator.count_status", "reported"]}, {"$gt": ["$denominator.count", 0]}]},
        {"$multiply": [{"$divide": [{"$toDecimal": "$selected.count"}, {"$toDecimal": "$denominator.count"}]}, Decimal128("100")]}, None]}
    return [{"$match": {"workplace_area": area, "survey_year": year}},
        {"$project": {"selected": selected}}, {"$set": {"denominator": denominator}},
        {"$unwind": "$selected"}, {"$match": {"selected.transport_mode_code": {"$in": list(MODES)}}},
        {"$project": {"_id": 0, "transport_mode_code": "$selected.transport_mode_code",
            "count": "$selected.count", "count_status": "$selected.count_status", "share_pct": share,
            "published_total": "$denominator.count", "denominator_status": "$denominator.count_status",
            "order": {"$indexOfArray": [list(MODES), "$selected.transport_mode_code"]}}},
        {"$sort": {"order": 1}}, {"$project": {"order": 0}}]
