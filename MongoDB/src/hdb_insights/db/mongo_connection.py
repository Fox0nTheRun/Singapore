"""MongoDB connection helper. Reuse clients within the application lifecycle."""
import os
import re
from pymongo import MongoClient
from pymongo.write_concern import WriteConcern


def connect():
    return MongoClient(os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/"),
        serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=15000,
        appname="hdb-insights", retryWrites=False)


def database(client, name=None):
    name = name or os.environ.get("MONGODB_DATABASE", "hdb_insights")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name) or name in ("admin", "config", "local"):
        raise ValueError("Invalid project database name")
    return client.get_database(name, write_concern=WriteConcern(w=1, wtimeout=10000))
