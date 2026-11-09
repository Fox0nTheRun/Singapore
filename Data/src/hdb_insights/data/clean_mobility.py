"""Lossless D08 wide-to-long reshape with explicit source-header mapping."""
from __future__ import annotations
import pandas as pd
MOBILITY_COLUMNS = {
    "Total_Total": ("ALL", "ALL"),
    "Total_ModeofTransport_CombinationsofRail_MRT_LRT_orPublicBus": ("ALL", "RAIL_BUS"),
    "Total_ModeofTransport_CarorTaxi_PrivateHireCarOnly": ("ALL", "CAR_TAXI_PRIVATE_HIRE"),
    "Total_ModeofTransport_OtherModes": ("ALL", "OTHER"),
    "Total_ModeofTransport_NoTransportRequired": ("ALL", "NO_TRANSPORT"),
    "CentralRegion_Total": ("CENTRAL", "ALL"),
    "CentralRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPubl": ("CENTRAL", "RAIL_BUS"),
    "CentralRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly": ("CENTRAL", "CAR_TAXI_PRIVATE_HIRE"),
    "CentralRegion_ModeofTransport_OtherModes": ("CENTRAL", "OTHER"),
    "CentralRegion_ModeofTransport_NoTransportRequired": ("CENTRAL", "NO_TRANSPORT"),
    "EastRegion_Total": ("EAST", "ALL"),
    "EastRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPublicB": ("EAST", "RAIL_BUS"),
    "EastRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly": ("EAST", "CAR_TAXI_PRIVATE_HIRE"),
    "EastRegion_ModeofTransport_OtherModes": ("EAST", "OTHER"),
    "EastRegion_ModeofTransport_NoTransportRequired": ("EAST", "NO_TRANSPORT"),
    "NorthRegion_Total": ("NORTH", "ALL"),
    "NorthRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPublic": ("NORTH", "RAIL_BUS"),
    "NorthRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly": ("NORTH", "CAR_TAXI_PRIVATE_HIRE"),
    "NorthRegion_ModeofTransport_OtherModes": ("NORTH", "OTHER"),
    "NorthRegion_ModeofTransport_NoTransportRequired": ("NORTH", "NO_TRANSPORT"),
    "North_EastRegion_Total": ("NORTH_EAST", "ALL"),
    "North_EastRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orP": ("NORTH_EAST", "RAIL_BUS"),
    "North_EastRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly": ("NORTH_EAST", "CAR_TAXI_PRIVATE_HIRE"),
    "North_EastRegion_ModeofTransport_OtherModes": ("NORTH_EAST", "OTHER"),
    "North_EastRegion_ModeofTransport_NoTransportRequired": ("NORTH_EAST", "NO_TRANSPORT"),
    "WestRegion_Total": ("WEST", "ALL"),
    "WestRegion_ModeofTransport_CombinationsofRail_MRT_LRT_orPublicB": ("WEST", "RAIL_BUS"),
    "WestRegion_ModeofTransport_CarorTaxi_PrivateHireCarOnly": ("WEST", "CAR_TAXI_PRIVATE_HIRE"),
    "WestRegion_ModeofTransport_OtherModes": ("WEST", "OTHER"),
    "WestRegion_ModeofTransport_NoTransportRequired": ("WEST", "NO_TRANSPORT"),
}
OUTPUT_HEADERS = ["survey_year","workplace_area","workplace_area_kind","residence_region_code","transport_mode_code","count","count_status","source_column","dataset_id","source_file_sha256","source_row_number"]
SPECIAL = {"Other Planning Areas or Outside Singapore", "No Fixed Location for Work", "Works from Home"}
def clean_mobility(raw_frame: pd.DataFrame, source_sha256: str):
    expected = ["Number", *MOBILITY_COLUMNS.keys()]
    if list(raw_frame.columns) != expected: raise ValueError(f"D08 headers mismatch. Expected {expected}; got {list(raw_frame.columns)}")
    rows, issues = [], []
    for row_num, src in enumerate(raw_frame.to_dict(orient="records"), start=1):
        workplace = str(src["Number"]).strip()
        if not workplace:
            issues.append({"severity":"error","dataset_id":"D08","source_row_number":row_num,"source_column":"Number","message":"empty workplace category","action":"quarantined"}); continue
        kind = "total" if workplace == "Total" else ("special" if workplace in SPECIAL else "planning_area")
        for col, (region, mode) in MOBILITY_COLUMNS.items():
            token = str(src[col]).strip()
            if token == "-": count, status = None, "unresolved_dash"
            elif token.isdigit(): count, status = int(token), "reported"
            else:
                issues.append({"severity":"error","dataset_id":"D08","source_row_number":row_num,"source_column":col,"raw_value":token,"message":"unexpected count token","action":"quarantined"}); continue
            rows.append({"survey_year":2020,"workplace_area":workplace,"workplace_area_kind":kind,"residence_region_code":region,"transport_mode_code":mode,"count":count,"count_status":status,"source_column":col,"dataset_id":"D08","source_file_sha256":source_sha256,"source_row_number":row_num})
    frame = pd.DataFrame(rows, columns=OUTPUT_HEADERS)
    # Mixed null + integer values must remain object-backed; otherwise pandas promotes counts to floats.
    frame["count"] = pd.Series([row["count"] for row in rows], dtype="object")
    if not frame.empty:
        dup = frame.duplicated(["survey_year","workplace_area","residence_region_code","transport_mode_code"], keep=False)
        if dup.any():
            for _, r in frame.loc[dup].iterrows(): issues.append({"severity":"error","dataset_id":"D08","source_row_number":int(r["source_row_number"]),"rule_id":"DUPLICATE_KEY","message":"duplicate mobility business key","action":"blocked"})
        frame = frame.sort_values(["source_row_number","residence_region_code","transport_mode_code"], kind="stable").reset_index(drop=True)
    return frame, issues
