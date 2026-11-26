"""Shared application service for both database backends.

The database adapters implement queries and CRUD operations.
No CSV-derived application answers, implicit writes, or connection caching.
"""
from __future__ import annotations

from contextlib import contextmanager
from importlib import import_module
import logging
import os
from typing import Any, Iterator

from .options import mongo_options_formatter

LOGGER = logging.getLogger(__name__)
CONTRACT_VERSION = "HDBI-1.0.0"
BACKENDS = ("mariadb", "mongodb")
PUBLIC_OPERATIONS = frozenset({
    "search_resale", "summarise_resale", "resale_trend", "demographic_profile",
    "mobility_breakdown", "list_filter_options", "create_demo_resale",
    "get_demo_resale", "update_demo_resale", "delete_demo_resale",
})


def failure(backend: str, code: str, message: str) -> dict:
    return {"ok": False, "data": None, "error": {"code": code, "message": message},
            "meta": {"backend": backend, "contract_version": CONTRACT_VERSION,
                     "data_release_id": None}}


@contextmanager
def backend_session(backend: str) -> Iterator[Any]:
    """Adapt module-based MariaDB and instance-based MongoDB behind one API."""
    if backend == "mariadb":
        # The MariaDB adapter is a module of functions with a new connection per call.
        if "MARIADB_PASSWORD" not in os.environ:
            raise RuntimeError("Set MARIADB_PASSWORD in the application environment for the hdb_app account.")
        yield import_module("hdb_insights.db.mariadb_repository")
    elif backend == "mongodb":
        adapter_cls = import_module("hdb_insights.db.mongodb_adapter").MongoDBAdapter
        adapter = adapter_cls(options_formatter=mongo_options_formatter)
        try:
            yield adapter
        finally:
            adapter.close()
    else:
        raise ValueError("Unsupported database backend")


def call(backend: str, operation: str, *args: Any, **kwargs: Any) -> dict:
    """Invoke one approved backend operation, preserving its result envelope.

    Important: an ambiguous create failure is NOT retried automatically.
    """
    if backend not in BACKENDS:
        return failure(str(backend), "VALIDATION_ERROR", "Choose MariaDB or MongoDB.")
    if operation not in PUBLIC_OPERATIONS:
        return failure(backend, "VALIDATION_ERROR", "Unsupported application operation.")
    try:
        with backend_session(backend) as adapter:
            reply = getattr(adapter, operation)(*args, **kwargs)
        if not isinstance(reply, dict) or not all(k in reply for k in ("ok", "data", "error", "meta")):
            return failure(backend, "INTERNAL_ERROR", "Backend returned an unexpected response format.")
        meta = reply["meta"]
        if (type(reply["ok"]) is not bool or not isinstance(meta, dict)
                or meta.get("backend") != backend):
            return failure(backend, "INTERNAL_ERROR", "Backend returned inconsistent response metadata.")
        if reply["ok"]:
            if (reply["error"] is not None or meta.get("contract_version") != CONTRACT_VERSION
                    or not meta.get("data_release_id")):
                return failure(backend, "DATA_NOT_READY", "Backend did not confirm a compatible published data release.")
        elif not isinstance(reply["error"], dict) or not reply["error"].get("code"):
            return failure(backend, "INTERNAL_ERROR", "Backend returned a malformed error response.")
        return reply
    except (ModuleNotFoundError, ImportError):
        LOGGER.exception("Missing backend dependency: %s", backend)
        return failure(backend, "DB_UNAVAILABLE", "Required database driver is missing. Install requirements-app.txt.")
    except TypeError:
        LOGGER.error("Database operation signature mismatch: %s.%s", backend, operation)
        return failure(backend, "INTERNAL_ERROR", "The application and database adapter interfaces do not match.")
    except RuntimeError as exc:
        LOGGER.warning("Application setup issue: %s", type(exc).__name__)
        return failure(backend, "DB_UNAVAILABLE", str(exc) if str(exc).startswith("Set MARIADB_PASSWORD") else "Backend configuration is incomplete.")
    except (ValueError, OSError) as exc:
        LOGGER.warning("Backend initialization issue: %s", type(exc).__name__)
        return failure(backend, "DB_UNAVAILABLE", "Unable to initialise database connection. Check local setup and credentials.")
    except Exception as exc:
        # Avoid leaking URIs, passwords or raw driver errors to the Streamlit UI.
        LOGGER.error("Unexpected backend error: %s / %s", backend, type(exc).__name__)
        return failure(backend, "DB_UNAVAILABLE", "The database could not be reached. Check the database service and connection settings.")
