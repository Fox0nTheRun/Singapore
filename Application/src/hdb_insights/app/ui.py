"""Streamlit frontend for INF2003 HDB Insights (Person D, Team 55).

Uses live MariaDB/MongoDB adapters only. Streamlit is not an analytics engine:
all filters, aggregation, and CRUD are delegated to the DB-owned repositories.
"""
from __future__ import annotations

from decimal import Decimal
import json

import pandas as pd
import streamlit as st

from .comparison import compare
from .options import unpack_options
from .services import call

AGE_LABELS = {"BELOW_15": "Below 15", "AGE_15_64": "Ages 15–64", "AGE_65_PLUS": "65 and above"}
MODE_LABELS = {"RAIL_BUS": "Rail and bus", "CAR_TAXI_PRIVATE_HIRE": "Car, taxi and private hire",
               "OTHER": "Other modes", "NO_TRANSPORT": "No transport"}


def _money(value, unit="$") -> str:
    if value is None:
        return "Not available"
    try:
        return f"{unit}{Decimal(str(value)):,.2f}"
    except (ValueError, ArithmeticError):
        return str(value)


def _num(value) -> str:
    if value is None:
        return "Not available"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _problem(result: dict) -> bool:
    if result.get("ok"):
        return False
    error = result.get("error") or {}
    st.error(f"{error.get('code', 'ERROR')}: {error.get('message', 'Operation failed')}")
    return True


def _options(backend: str, domain: str):
    result = call(backend, "list_filter_options", domain)
    if _problem(result):
        st.info("This view needs a connected database with a published release. See SETUP_PERSON_D.md.")
        st.stop()
    try:
        return unpack_options(result, domain)
    except (KeyError, ValueError) as exc:
        st.error(f"Incompatible {domain} dropdown response: {exc}")
        st.stop()


def _release_caption(result):
    meta = result.get("meta") or {}
    st.caption(f"Backend: {meta.get('backend', 'unknown')} · Contract: {meta.get('contract_version', 'unknown')} · Release: {meta.get('data_release_id') or 'unavailable'}")


def _resale_form(backend: str, key: str):
    opts = _options(backend, "resale")
    town_names = [None] + sorted(opts.get("town_names", []))
    flats = [None] + [x["flat_type_code"] for x in opts.get("flat_types", [])]
    flat_label = {x["flat_type_code"]: x.get("display_label", x["flat_type_code"]) for x in opts.get("flat_types", [])}
    months = [None] + sorted(opts.get("registration_months", []))
    with st.form(f"resale_{key}"):
        a, b = st.columns(2)
        with a:
            town = st.selectbox("Town", town_names, format_func=lambda x: "All towns" if x is None else x, key=f"{key}_town")
            start = st.selectbox("From month", months, format_func=lambda x: "Any month" if x is None else x, key=f"{key}_from")
        with b:
            flat = st.selectbox("Flat type", flats, format_func=lambda x: "All flat types" if x is None else flat_label.get(x, x), key=f"{key}_flat")
            end = st.selectbox("To month", months, index=len(months)-1, format_func=lambda x: "Any month" if x is None else x, key=f"{key}_to")
        c, d = st.columns(2)
        with c:
            limit = st.selectbox("Results per page", [10, 25, 50, 100], index=1, key=f"{key}_limit")
        with d:
            page = st.number_input("Page", min_value=1, step=1, value=1, key=f"{key}_page")
        submitted = st.form_submit_button("Run database queries", type="primary", use_container_width=True)
    filters = {k: v for k, v in {"town_name": town, "flat_type_code": flat, "start_month": start, "end_month": end}.items() if v is not None}
    if start and end and start > end:
        st.warning("The start month must not be after the end month.")
        submitted = False
    return filters, limit, (int(page) - 1) * limit, submitted


def _display_resale(search, summary, trend):
    if any(_problem(x) for x in (search, summary, trend)):
        return
    releases = {(r.get("meta") or {}).get("data_release_id") for r in (search, summary, trend)}
    versions = {(r.get("meta") or {}).get("contract_version") for r in (search, summary, trend)}
    if len(releases) != 1 or None in releases or len(versions) != 1:
        st.error("Backend release metadata changed across the three queries. Re-run the analysis after database maintenance.")
        return
    data = search["data"] or {}
    stats = summary["data"] or {}
    a, b, c = st.columns(3)
    a.metric("Matched resale transactions", _num(stats.get("transaction_count")))
    b.metric("Average resale price", _money(stats.get("average_price")))
    c.metric("Average price / m²", _money(stats.get("average_price_per_sqm")))
    _release_caption(search)
    st.subheader("Resale transaction records")
    st.caption(f"Page contains {len(data.get('rows') or [])} records out of {_num(data.get('total_count', 0))} matching transactions. Results are ordered by registration month and record ID.")
    rows = data.get("rows") or []
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
    else:
        st.info("No resale transactions match the selected filters.")
    st.subheader("Monthly average resale price")
    trends = (trend.get("data") or {}).get("rows") or []
    if trends:
        chart_rows = [{"Month": r["registration_month"], "Average resale price ($)": float(r["average_price"])}
                      for r in trends if r.get("average_price") is not None]
        if chart_rows:
            st.line_chart(pd.DataFrame(chart_rows).set_index("Month"), use_container_width=True)
        with st.expander("Show monthly aggregates"):
            st.dataframe(trends, hide_index=True, use_container_width=True)
    else:
        st.info("No monthly trends are available for these filters.")


def resale_page(backend: str):
    st.title("HDB Resale Explorer")
    st.write("Search transaction-level resale records and analyse database-calculated averages and monthly trends.")
    filters, limit, offset, submitted = _resale_form(backend, "explorer")
    if submitted:
        st.session_state["resale_run"] = {
            "backend": backend,
            "search": call(backend, "search_resale", filters, limit=limit, offset=offset),
            "summary": call(backend, "summarise_resale", filters),
            "trend": call(backend, "resale_trend", filters),
        }
    results = st.session_state.get("resale_run")
    if results and results["backend"] == backend:
        _display_resale(results["search"], results["summary"], results["trend"])
    else:
        st.info("Choose your filters and run the queries to display database results.")


def _demo_profile_inputs(backend: str, key: str):
    opts = _options(backend, "demographic")
    profiles = opts.get("profiles") or []
    if not profiles:
        st.warning("No demographic profiles were returned by the database.")
        st.stop()
    with st.container():
        groups = sorted(set(p["group_type"] for p in profiles))
        group = st.selectbox("Group by", groups, format_func=lambda x: "Flat type" if x == "flat_type" else "Ethnicity")
        matching = [p for p in profiles if p["group_type"] == group]
        codes = sorted(set(p["group_code"] for p in matching))
        labels = {p["group_code"]: p.get("display_label", p["group_code"]) for p in matching}
        group_code = st.selectbox("Category", codes, format_func=lambda x: labels.get(x, x))
        years = sorted(set(int(p["survey_year"]) for p in matching if p["group_code"] == group_code))
        year = st.selectbox("Survey year", years)
        submitted = st.button("Load demographic profile", type="primary", use_container_width=True, key=key)
    return (group, group_code, int(year)), submitted


def demographic_page(backend: str):
    st.title("Resident Demographics")
    st.write("Compare published HDB resident age distributions and population statistics by flat type or ethnicity.")
    params, submitted = _demo_profile_inputs(backend, "demographic_form")
    if submitted:
        st.session_state["demographic_run"] = {"backend": backend, "result": call(backend, "demographic_profile", *params)}
    saved = st.session_state.get("demographic_run")
    if not saved or saved["backend"] != backend:
        st.info("Select a category and survey year to view its published profile.")
        return
    result = saved["result"]
    if _problem(result):
        return
    _release_caption(result)
    data = result["data"]
    if data is None:
        st.info((result.get("meta") or {}).get("note", "No published profile for this selection."))
        return
    a,b,c = st.columns(3)
    a.metric("Average age", _money(data.get("average_age"), unit="").replace("Not available", "Unknown"))
    b.metric("Median age", _money(data.get("median_age"), unit="").replace("Not available", "Unknown"))
    c.metric("Population aged 15+", _num(data.get("population_15_plus")))
    if data.get("population_status") == "not_provided":
        st.caption("A population figure was not published for this aggregate. It has not been inferred.")
    ages = data.get("age_distribution") or []
    st.subheader("Age distribution (published percentages)")
    age_data = [{"Age group": AGE_LABELS.get(r["age_group_code"], r["age_group_code"]),
                 "Percentage": float(r["percentage"])} for r in ages]
    if age_data:
        st.bar_chart(pd.DataFrame(age_data).set_index("Age group"), use_container_width=True)
        st.dataframe(age_data, hide_index=True, use_container_width=True)
    st.caption("Age-distribution percentages can include people below 15, while population counts apply only to residents aged 15+. Published percentages may reflect rounding.")
    with st.expander("Source-row provenance"):
        st.dataframe(data.get("source_rows") or [], hide_index=True, use_container_width=True)


def _mobility_inputs(backend: str, key: str):
    options = _options(backend, "mobility")
    selections = options.get("selections") or []
    if not selections:
        st.info("No mobility categories were returned.")
        st.stop()
    with st.container():
        areas = sorted(set(x["workplace_area"] for x in selections))
        area = st.selectbox("Workplace area / workplace category", areas)
        regions = sorted(set(x["residence_region_code"] for x in selections if x["workplace_area"] == area))
        region = st.selectbox("Region of residence", regions, index=regions.index("ALL") if "ALL" in regions else 0,
                              format_func=lambda x: "All residence regions (published total)" if x == "ALL" else x.replace("_", " ").title())
        years = sorted(set(int(x["survey_year"]) for x in selections
                           if x["workplace_area"] == area and x["residence_region_code"] == region))
        year = st.selectbox("Survey year", years)
        submitted = st.button("Show transport breakdown", type="primary", use_container_width=True, key=key)
    return (area, region, int(year)), submitted


def mobility_page(backend: str):
    st.title("Workplace & Mobility")
    st.write("Explore published commuting statistics by place-of-work category and **region of residence**. Some workplace entries are special categories (such as working from home), not geographical planning areas.")
    params, submitted = _mobility_inputs(backend, "mobility_form")
    if submitted:
        st.session_state["mobility_run"] = {"backend": backend, "result": call(backend, "mobility_breakdown", *params)}
    saved = st.session_state.get("mobility_run")
    if not saved or saved["backend"] != backend:
        st.info("Select an area and region to load a database breakdown.")
        return
    result = saved["result"]
    if _problem(result):
        return
    _release_caption(result)
    data = result.get("data") or {}
    st.metric("Published total", _num(data.get("published_total")))
    rows = data.get("rows") or []
    display_rows = [{"Transport mode": MODE_LABELS.get(r["transport_mode_code"], r["transport_mode_code"]),
                     "Resident count": r.get("count"), "Count status": r.get("count_status"),
                     "Share of published total (%)": r.get("share_pct")} for r in rows]
    st.dataframe(display_rows, hide_index=True, use_container_width=True)
    known = [{"Transport mode": x["Transport mode"], "Count": int(x["Resident count"])}
             for x in display_rows if x["Resident count"] is not None]
    if known:
        st.bar_chart(pd.DataFrame(known).set_index("Transport mode"), use_container_width=True)
    st.caption(data.get("note") or "Counts marked unresolved_dash are unknown, not zero. Shares use the published ALL-mode total and are not renormalised.")


def _demo_business_form(seed: dict, key: str, *, include_seed: bool):
    """Collect backend-compatible typed business fields without changing lineage."""
    with st.form(key):
        if include_seed:
            st.caption("New demo records use the selected, registered source transaction as their seed. Source records stay unchanged.")
        a, b, c = st.columns(3)
        with a:
            registration_month = st.text_input("Registration month (YYYY-MM)", seed.get("registration_month", "2017-01"))
            town_name = st.text_input("Town name", seed.get("town_name", ""))
            flat_type_code = st.text_input("Flat type code", seed.get("flat_type_code", ""))
            block = st.text_input("Block", seed.get("block", ""))
        with b:
            street_name = st.text_input("Street name", seed.get("street_name", ""))
            flat_model = st.text_input("Flat model", seed.get("flat_model", ""))
            storey_lower = st.number_input("Storey lower", min_value=0, value=int(seed.get("storey_lower", 1)))
            storey_upper = st.number_input("Storey upper", min_value=0, value=int(seed.get("storey_upper", 3)))
        with c:
            floor_area_sqm = st.text_input("Floor area (m²)", str(seed.get("floor_area_sqm", "")))
            resale_price = st.text_input("Resale price ($)", str(seed.get("resale_price", "")))
            lease_commence_year = st.number_input("Lease commencement year", min_value=1, max_value=9999, value=int(seed.get("lease_commence_year", 1990)))
            remaining_lease_months = st.number_input("Remaining lease (months)", min_value=0, value=int(seed.get("remaining_lease_months", 0)))
        submitted = st.form_submit_button("Create demo record" if include_seed else "Save edited demo record", type="primary")
    data = {"registration_month": registration_month.strip(), "town_name": town_name.strip(),
            "flat_type_code": flat_type_code.strip(), "block": block.strip(), "street_name": street_name.strip(),
            "storey_lower": int(storey_lower), "storey_upper": int(storey_upper), "floor_area_sqm": floor_area_sqm.strip(),
            "flat_model": flat_model.strip(), "lease_commence_year": int(lease_commence_year),
            "remaining_lease_months": int(remaining_lease_months), "resale_price": resale_price.strip()}
    return data, submitted


def demo_page(backend: str):
    st.title("Safe CRUD Demonstration")
    st.write("Create, read, update and delete **demo records only**. Analytical resale transactions are read-only.")
    st.info("MariaDB's handover registers only the first 10 original resale records as demo seeds. Do not use arbitrary search results as seed IDs; no seed provisioning is performed by the frontend.")
    tabs = st.tabs(["Create", "Read", "Update", "Delete"])
    with tabs[0]:
        seed_result = call(backend, "search_resale", {}, limit=10, offset=0)
        if not _problem(seed_result):
            seeds = (seed_result.get("data") or {}).get("rows") or []
            if seeds:
                labels = [f"{str(row['record_id'])[-9:]} · {row['town_name']} · {row['flat_type_code']} · {row['registration_month']}" for row in seeds]
                selected = st.selectbox("Source seed record (initial 10)", range(len(seeds)), format_func=lambda x: labels[x])
                source = seeds[selected]
                payload, submitted = _demo_business_form(source, f"create_{backend}_{selected}", include_seed=True)
                if submitted:
                    result = call(backend, "create_demo_resale", {"seed_record_id": source["record_id"], **payload})
                    if not _problem(result):
                        identity = (result["data"] or {}).get("demo_record_id")
                        st.session_state[f"demo_id_{backend}"] = identity
                        st.success(f"Created demo record: {identity}")
                        st.json(result["data"])
                    else:
                        st.warning("If a Create acknowledgement was lost, inspect existing demo records before trying again. Do not blindly retry.")
            else:
                st.info("There are no analytical records available for demo seeding.")
    with tabs[1]:
        identity = st.text_input("Demo record ID to read", value=st.session_state.get(f"demo_id_{backend}") or "", key=f"read_id_{backend}")
        if st.button("Read demo record", key=f"read_{backend}"):
            result = call(backend, "get_demo_resale", identity)
            if not _problem(result):
                _release_caption(result)
                st.json(result["data"])
                st.session_state[f"last_read_{backend}"] = result["data"]
    with tabs[2]:
        st.caption("Read the record in the Read tab first, then edit its business fields. Immutable identity and provenance cannot be changed.")
        record = st.session_state.get(f"last_read_{backend}")
        if record:
            st.code(record["demo_record_id"])
            fields, submitted = _demo_business_form(record, f"update_{backend}_{record['demo_record_id']}", include_seed=False)
            if submitted:
                result = call(backend, "update_demo_resale", record["demo_record_id"], fields)
                if not _problem(result):
                    st.success("Demo record updated.")
                    st.session_state[f"last_read_{backend}"] = result["data"]
                    st.json(result["data"])
        else:
            st.info("Read a demo record to enable editing.")
    with tabs[3]:
        identity = st.text_input("Demo record ID to delete", value=st.session_state.get(f"demo_id_{backend}") or "", key=f"delete_id_{backend}")
        acknowledged = st.checkbox("I understand this action removes a demo record, not an analytical source record.", key=f"delete_confirm_{backend}")
        if st.button("Delete demo record", disabled=not acknowledged or not identity.strip(), key=f"delete_{backend}"):
            result = call(backend, "delete_demo_resale", identity)
            if not _problem(result):
                st.success("Demo record deleted.")
                if st.session_state.get(f"demo_id_{backend}") == identity:
                    st.session_state[f"demo_id_{backend}"] = ""
                if (st.session_state.get(f"last_read_{backend}") or {}).get("demo_record_id") == identity:
                    st.session_state.pop(f"last_read_{backend}", None)


def comparison_page():
    st.title("MariaDB vs MongoDB")
    st.write("Run the same read-only queries against each backend. Values are compared only when both use the same published contract and release.")
    st.caption("This is a correctness comparison, not a timed benchmark. For performance claims, Xi Fa must collect repeatable measurements and matching query conditions.")
    domain = st.radio("Query family", ["Resale", "Demographics", "Mobility"], horizontal=True)
    if domain == "Resale":
        filters, limit, offset, submitted = _resale_form("mariadb", "comparison")
        operation = st.selectbox("Equivalent operation", ["summarise_resale", "resale_trend", "search_resale"], format_func=lambda x: x.replace("_", " ").title())
        params = (filters,)
        kwargs = {"limit": limit, "offset": offset} if operation == "search_resale" else {}
    elif domain == "Demographics":
        params, submitted = _demo_profile_inputs("mariadb", "compare_demo_form")
        operation, kwargs = "demographic_profile", {}
    else:
        params, submitted = _mobility_inputs("mariadb", "compare_mobility_form")
        operation, kwargs = "mobility_breakdown", {}
    if submitted:
        st.session_state["comparison_run"] = {"domain": domain, "result": compare(operation, *params, **kwargs), "operation": operation}
    saved = st.session_state.get("comparison_run")
    if not saved or saved["domain"] != domain:
        st.info("Select your query and run it to compare live results.")
        return
    result = saved["result"]
    status = result["status"]
    if status == "match":
        st.success("Both databases returned equivalent values for the selected query.")
    elif status == "mismatch":
        st.warning("The databases returned different values. Review the mismatch paths.")
    else:
        st.warning("Comparison cannot be completed until both backends respond on the same active release.")
    if result["differences"]:
        for issue in result["differences"]:
            st.write(f"• {issue}")
    left, right = st.columns(2)
    with left:
        st.subheader("MariaDB")
        _release_caption(result["mariadb"])
        if not _problem(result["mariadb"]):
            st.json(result["mariadb"]["data"], expanded=False)
    with right:
        st.subheader("MongoDB")
        _release_caption(result["mongodb"])
        if not _problem(result["mongodb"]):
            st.json(result["mongodb"]["data"], expanded=False)


def about_page(backend: str):
    st.title("HDB Insights")
    st.subheader("Housing · Demographics · Mobility")
    st.write("An INF2003 Database Systems group application comparing relational and document-oriented database designs for eight Singapore public datasets.")
    st.markdown("**Explore:** Resale transaction search and trends, published resident demographics, workplace mobility, safe demo CRUD, and equivalent queries across MariaDB and MongoDB.")
    st.markdown("**Data principles:** Never replace missing counts with zero, never synthesise cross-dataset relationships, and never modify published analytical transactions through the interface.")
    st.subheader("Connection status")
    result = call(backend, "list_filter_options", "resale")
    if result["ok"]:
        st.success(f"{backend.title()} is connected to a compatible active release.")
    else:
        _problem(result)
        st.info("If you have not configured local databases, follow SETUP_PERSON_D.md before testing connected pages.")
    _release_caption(result)
    st.subheader("Team 55 implementation layers")
    st.dataframe([
        {"Layer": "Prepared data", "Owner": "Xavier", "Role": "Validated and transformed eight datasets"},
        {"Layer": "Relational backend", "Owner": "Chang Rong", "Role": "MariaDB schema, loader, queries and demo CRUD"},
        {"Layer": "Document backend", "Owner": "Isaac", "Role": "MongoDB collections, loader, pipelines and demo CRUD"},
        {"Layer": "Application and frontend", "Owner": "Bill", "Role": "Shared backend calls, Streamlit pages and dropdown coordination"},
        {"Layer": "Comparison evidence", "Owner": "Xi Fa", "Role": "Independent equivalence tests and controlled measurements"},
    ], hide_index=True, use_container_width=True)


def main():
    st.set_page_config(page_title="HDB Insights | INF2003", page_icon="🏙️", layout="wide")
    st.markdown("""<style>
      .block-container { max-width: 1260px; padding-top: 2rem; }
      div[data-testid="stMetric"] { border:1px solid rgba(128,128,128,.20); border-radius:12px; padding: 12px; }
      h1 { letter-spacing: -.035em; }
      div[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.18); }
    </style>""", unsafe_allow_html=True)
    with st.sidebar:
        st.title("🏙️ HDB Insights")
        st.caption("INF2003 · Team 55")
        backend = st.selectbox("Database backend", ("mariadb", "mongodb"), format_func=lambda x: "MariaDB (SQL)" if x == "mariadb" else "MongoDB (NoSQL)")
        page = st.radio("Navigate", ["Overview", "Resale Explorer", "Demographics", "Mobility Explorer", "CRUD Demo", "Database Comparison"])
        st.divider()
        st.caption("Expected release: 150921447b27_c1.0.0_t0.1.2")
        st.caption("Read-only analytical datasets · Writes restricted to demo data")
    if page == "Overview": about_page(backend)
    elif page == "Resale Explorer": resale_page(backend)
    elif page == "Demographics": demographic_page(backend)
    elif page == "Mobility Explorer": mobility_page(backend)
    elif page == "CRUD Demo": demo_page(backend)
    else: comparison_page()


if __name__ == "__main__":
    main()
