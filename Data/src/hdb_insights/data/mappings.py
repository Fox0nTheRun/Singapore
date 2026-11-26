"""Central source mappings for HDBI-1.0.0."""
from pathlib import Path

DATASETS = {
    "D01": {
        "filename": "Resale flat prices based on registration date from Jan-2017 onwards.csv",
        "headers": ["month", "town", "flat_type", "block", "street_name", "storey_range",
                    "floor_area_sqm", "flat_model", "lease_commence_date", "remaining_lease", "resale_price"],
        "output": "resale.csv",
    },
    "D02": {"filename": "Age of HDB Resident Population by Flat Type.csv",
            "headers": ["shs_year", "flat_type", "age_group", "percentage"], "output": "age_by_flat_type.csv"},
    "D03": {"filename": "Average and Median Age of HDB Resident Population by Flat Type.csv",
            "headers": ["shs_year", "flat_type", "average_age", "median_age"], "output": "age_stats_by_flat_type.csv"},
    "D04": {"filename": "HDB Resident Population Aged 15 Years and Above by Flat Type.csv",
            "headers": ["shs_year", "flat_type", "number"], "output": "population_15_plus_by_flat_type.csv"},
    "D05": {"filename": "Age of HDB Resident Population by Ethnic Group.csv",
            "headers": ["shs_year", "ethnic_group", "age_group", "percentage"], "output": "age_by_ethnicity.csv"},
    "D06": {"filename": "Average and Median Age of HDB Population by Ethnic Group.csv",
            "headers": ["shs_year", "ethnic_group", "average_age", "median_age"], "output": "age_stats_by_ethnicity.csv"},
    "D07": {"filename": "HDB Resident Population Aged 15 Years and Above by Ethnic Group.csv",
            "headers": ["shs_year", "ethnic_group", "number"], "output": "population_15_plus_by_ethnicity.csv"},
    "D08": {"filename": "EmployedResidentsAged15YearsandOverbyPlanningAreaofWorkplaceUsu.csv",
            "headers": None, "output": "mobility.csv"},
}
FLAT_TYPE = {
    "1 ROOM": "1_ROOM", "1-ROOM": "1_ROOM", "1-ROOM": "1_ROOM",
    "2 ROOM": "2_ROOM", "2-ROOM": "2_ROOM", "3 ROOM": "3_ROOM", "3-ROOM": "3_ROOM",
    "4 ROOM": "4_ROOM", "4-ROOM": "4_ROOM", "5 ROOM": "5_ROOM", "5-ROOM": "5_ROOM",
    "EXECUTIVE": "EXECUTIVE", "MULTI-GENERATION": "MULTI_GENERATION", "ALL": "ALL",
}
ETHNICITY = {"CHINESE": "CHINESE", "MALAY": "MALAY", "INDIAN": "INDIAN", "OTHERS": "OTHERS", "ALL": "ALL"}
AGE_GROUP = {"BELOW 15": "BELOW_15", "15-64": "AGE_15_64", "65 & ABOVE": "AGE_65_PLUS"}
