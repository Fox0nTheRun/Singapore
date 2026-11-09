"""Opt-in checks on a separately configured real application account.

The write probe matches no valid record ID, never upserts, and cannot edit data.
Authentication/privilege tests are skipped without an explicit application URI.
"""
import os
import pytest
from bson.decimal128 import Decimal128
from pymongo import MongoClient
from pymongo.errors import OperationFailure


def test_T_C_15_actual_application_privileges():
    uri = os.environ.get("HDBI_APP_TEST_MONGODB_URI")
    if os.environ.get("HDBI_RUN_MONGO_TESTS") != "1" or not uri:
        pytest.skip("Application permission acceptance needs explicit HDBI_APP_TEST_MONGODB_URI")
    database_name = os.environ.get("MONGODB_DATABASE", "hdb_insights")
    with MongoClient(uri, serverSelectionTimeoutMS=5000, socketTimeoutMS=15000) as client:
        privileges = client.admin.command({"connectionStatus": 1, "showPrivileges": True})["authInfo"]
        assert privileges.get("authenticatedUsers"), "No authenticated application account; privilege separation is unverified"
        mutating = {"anyAction", "insert", "update", "remove", "dropCollection", "dropDatabase", "createCollection", "collMod", "bypassDocumentValidation", "renameCollectionSameDB", "createIndex", "dropIndex"}
        for privilege in privileges.get("authenticatedUserPrivileges", []):
            resource = privilege["resource"]
            affects_analytics = resource.get("anyResource") or ("db" in resource and resource["db"] in ("", database_name))
            assert not (affects_analytics and set(privilege["actions"]) & mutating), "Application account has analytical mutation privileges"
        with pytest.raises(OperationFailure) as exc:
            client[database_name].resale_transactions.update_one(
                {"_id": "__permission_probe_not_a_valid_D01_identity__"},
                {"$set": {"resale_price": Decimal128("1.00")}}, upsert=False)
        assert exc.value.code == 13
