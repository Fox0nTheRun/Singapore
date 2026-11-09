"""Unit/contract checks without real MariaDB or MongoDB infrastructure."""
from contextlib import contextmanager
from decimal import Decimal

import pytest

from hdb_insights.app import comparison, options, services

RELEASE = "150921447b27_c1.0.0_t0.1.2"


def reply(backend="mariadb", data=None, *, error=None, release=RELEASE):
    return {"ok": error is None, "data": data if error is None else None, "error": error,
            "meta": {"backend": backend, "contract_version": "HDBI-1.0.0", "data_release_id": release}}


def test_mongo_resale_options_normalize():
    result = options.mongo_options_formatter("resale", {"town_name": ["BEDOK", "BEDOK", "ANG MO KIO"],
        "flat_type_code": ["3_ROOM", "4_ROOM"], "registration_month": ["2017-02", "2017-01"]})
    assert result["town_names"] == ["ANG MO KIO", "BEDOK"]
    assert result["flat_types"] == [
        {"flat_type_code": "3_ROOM", "display_label": "3-room"},
        {"flat_type_code": "4_ROOM", "display_label": "4-room"}]
    assert result["registration_months"] == ["2017-01", "2017-02"]


def test_mongo_demographic_options_normalize():
    raw = {"profiles": [{"group_type": "ethnicity", "group_code": "ALL", "survey_year": 2018}]}
    assert options.mongo_options_formatter("demographic", raw)["profiles"][0]["display_label"].startswith("All")


def test_mobility_options_all_regions():
    raw = {"workplaces": [{"workplace_area": "Total", "survey_year": 2020}],
           "residence_region_code": ["ALL", "CENTRAL", "WEST"]}
    values = options.mongo_options_formatter("mobility", raw)["selections"]
    assert len(values) == 3
    assert {p["residence_region_code"] for p in values} == {"ALL", "CENTRAL", "WEST"}


def test_service_rejects_unapproved_operation():
    result = services.call("mariadb", "drop_tables")
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_missing_mariadb_password_returns_safe_error(monkeypatch):
    monkeypatch.delenv("MARIADB_PASSWORD", raising=False)
    result = services.call("mariadb", "search_resale", {})
    assert result["error"]["code"] == "DB_UNAVAILABLE"
    assert "MARIADB_PASSWORD" in result["error"]["message"]


def test_service_calls_adapter_and_preserves_contract(monkeypatch):
    class Stub:
        def search_resale(self, filters, limit=50, offset=0):
            return reply(backend="mongodb", data={"rows": [], "limit": limit, "offset": offset, "total_count": 0})

    @contextmanager
    def session(backend):
        assert backend == "mongodb"
        yield Stub()

    monkeypatch.setattr(services, "backend_session", session)
    result = services.call("mongodb", "search_resale", {}, limit=15, offset=10)
    assert result["ok"]
    assert result["data"]["limit"] == 15
    assert result["data"]["offset"] == 10


def test_comparison_reports_equivalent_rounded_numeric_data(monkeypatch):
    def mock_call(backend, operation, *args, **kwargs):
        assert operation == "summarise_resale"
        avg = "325001.30" if backend == "mariadb" else "325001.300000"
        return reply(backend=backend, data={"transaction_count": 3, "average_price": avg,
                    "average_price_per_sqm": "3000.52"})
    monkeypatch.setattr(comparison, "call", mock_call)
    assert comparison.compare("summarise_resale", {})["status"] == "match"


def test_comparison_rejects_different_releases(monkeypatch):
    def mock_call(backend, *args, **kwargs):
        return reply(backend=backend, data={"transaction_count": 1}, release=RELEASE if backend == "mariadb" else "old")
    monkeypatch.setattr(comparison, "call", mock_call)
    result = comparison.compare("summarise_resale", {})
    assert result["status"] == "not_comparable"
    assert "release" in result["differences"][0]


def test_comparison_preserves_unknown_nulls(monkeypatch):
    def mock_call(backend, *args, **kwargs):
        return reply(backend=backend, data={"rows": [{"transport_mode_code": "RAIL_BUS",
            "count": None if backend == "mariadb" else 0, "count_status": "unresolved_dash",
            "share_pct": None}], "published_total": 100})
    monkeypatch.setattr(comparison, "call", mock_call)
    assert comparison.compare("mobility_breakdown", "Total", "ALL", 2020)["status"] == "mismatch"


def test_comparison_differences_no_sensitive_data():
    found = comparison.differences({"secret": "alpha"}, {"secret": "beta"})
    assert found == ["data.secret: values differ"]
    assert "alpha" not in str(found) and "beta" not in str(found)


def test_payload_with_decimals_is_not_precomputed():
    assert comparison.canonical("100.000", "resale_price") == Decimal("100.00")
    assert comparison.canonical("001", "block") == "001"
    assert comparison.canonical(None) is None


# Tests added after receiving C's actual original ZIP (2026-10-30 handover).
def test_mongo_dropdown_labels_match_mariadb_seeded_categories():
    from hdb_insights.app.options import FLAT_LABELS, ETHNIC_LABELS
    resale = options.mongo_options_formatter("resale", {
        "town_name": ["BEDOK"], "flat_type_code": ["1_ROOM", "EXECUTIVE", "MULTI_GENERATION"],
        "registration_month": ["2020-01"]})
    assert {r["flat_type_code"]: r["display_label"] for r in resale["flat_types"]} == {
        "1_ROOM": "1-room", "EXECUTIVE": "Executive", "MULTI_GENERATION": "Multi-generation"}
    demographic = options.mongo_options_formatter("demographic", {"profiles": [
        {"group_type": "flat_type", "group_code": "ALL", "survey_year": 2018},
        {"group_type": "ethnicity", "group_code": "ALL", "survey_year": 2018}]})
    assert {(r["group_type"], r["display_label"]) for r in demographic["profiles"]} == {
        ("flat_type", "All flat types"), ("ethnicity", "All ethnic groups")}
    assert FLAT_LABELS["EXECUTIVE"] == "Executive"
    assert ETHNIC_LABELS["OTHERS"] == "Others"


def test_invalid_options_nesting_is_rejected():
    with pytest.raises(ValueError, match="malformed"):
        options.unpack_options(reply(data={"options": {"town_names": "ANG MO KIO"}}), "resale")
    with pytest.raises(ValueError, match="Unknown"):
        options.unpack_options(reply(data={"options": {}}), "invalid")


def test_mongo_adapter_lifecycle_is_closed_and_formatter_injected(monkeypatch):
    from types import SimpleNamespace
    events = []
    class C:
        def __init__(self, *, options_formatter=None):
            assert options_formatter is options.mongo_options_formatter
            events.append("open")
        def close(self):
            events.append("close")
        def search_resale(self, filters, limit=50, offset=0):
            return reply(backend="mongodb", data={"rows": [], "total_count": 0, "limit": limit, "offset": offset})
    monkeypatch.setattr(services, "import_module", lambda name: SimpleNamespace(MongoDBAdapter=C))
    actual = services.call("mongodb", "search_resale", {}, limit=25, offset=0)
    assert actual["ok"] and events == ["open", "close"]


def test_reject_success_without_release(monkeypatch):
    @contextmanager
    def session(_backend):
        class Bad:
            def search_resale(self, filters):
                return reply(backend="mongodb", data={"rows": []}, release=None)
        yield Bad()
    monkeypatch.setattr(services, "backend_session", session)
    result = services.call("mongodb", "search_resale", {})
    assert not result["ok"] and result["error"]["code"] == "DATA_NOT_READY"


def test_reject_wrong_backend_metadata(monkeypatch):
    @contextmanager
    def session(_backend):
        class Bad:
            def search_resale(self, filters):
                return reply(backend="mariadb", data={"rows": []})
        yield Bad()
    monkeypatch.setattr(services, "backend_session", session)
    result = services.call("mongodb", "search_resale", {})
    assert result["error"]["code"] == "INTERNAL_ERROR"


def test_wrong_adapter_signature_is_flagged_as_contract_error(monkeypatch):
    @contextmanager
    def session(_backend):
        class Wrong:
            def search_resale(self):
                return reply(backend="mongodb", data={})
        yield Wrong()
    monkeypatch.setattr(services, "backend_session", session)
    result = services.call("mongodb", "search_resale", {})
    assert result["error"]["code"] == "INTERNAL_ERROR"
    assert "interfaces do not match" in result["error"]["message"]


def test_mobility_comparison_ignores_only_backend_wording(monkeypatch):
    def mock_call(backend, *args, **kwargs):
        data = {"rows": [{"transport_mode_code": "RAIL_BUS", "count": None,
                  "count_status": "unresolved_dash", "share_pct": None}],
                "published_total": 0, "note": "SQL note" if backend == "mariadb" else "MongoDB note"}
        return reply(backend=backend, data=data)
    monkeypatch.setattr(comparison, "call", mock_call)
    assert comparison.compare("mobility_breakdown", "Total", "NORTH", 2020)["status"] == "match"


def test_mongo_provenance_and_integer_zero_are_not_discarded():
    assert comparison.canonical({"count": 0, "count_status": "reported"}) != comparison.canonical({"count": None, "count_status": "unresolved_dash"})


def test_integer_comparison_does_not_round_fractional_counts():
    assert comparison.canonical("1.001", "count") != comparison.canonical(1, "count")
    assert comparison.canonical("1", "count") == comparison.canonical(1, "count")
