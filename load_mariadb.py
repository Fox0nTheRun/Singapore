"""Initial MariaDB load for HDB Insights, contract HDBI-1.0.0."""

import csv
import getpass
import hashlib
import io
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import mariadb


ROOT = Path(__file__).resolve().parent
RELEASE = "150921447b27_c1.0.0_t0.1.2"
CONTRACT = "HDBI-1.0.0"
FOLDER = ROOT / "data" / "processed" / RELEASE

# Explicit table names: never accept SQL identifiers from a CSV.
TABLES = {
    "resale.csv": "resale_transaction",
    "age_by_flat_type.csv": "age_by_flat_type",
    "age_stats_by_flat_type.csv": "age_stats_by_flat_type",
    "population_15_plus_by_flat_type.csv":
        "population_15_plus_by_flat_type",
    "age_by_ethnicity.csv": "age_by_ethnicity",
    "age_stats_by_ethnicity.csv": "age_stats_by_ethnicity",
    "population_15_plus_by_ethnicity.csv":
        "population_15_plus_by_ethnicity",
    "mobility.csv": "mobility_observation",
}

INTEGER_FIELDS = {
    "survey_year", "storey_lower", "storey_upper",
    "lease_commence_year", "remaining_lease_months",
    "population_15_plus", "count", "source_row_number",
}

DECIMAL_FIELDS = {
    "floor_area_sqm", "resale_price", "percentage",
    "average_age", "median_age",
}

FLATS = {
    "1_ROOM": "1-room",
    "2_ROOM": "2-room",
    "3_ROOM": "3-room",
    "4_ROOM": "4-room",
    "5_ROOM": "5-room",
    "EXECUTIVE": "Executive",
    "MULTI_GENERATION": "Multi-generation",
    "ALL": "All flat types",
}

ETHNICITIES = {
    "CHINESE": "Chinese",
    "MALAY": "Malay",
    "INDIAN": "Indian",
    "OTHERS": "Others",
    "ALL": "All ethnic groups",
}

AGES = [
    ("BELOW_15", "Below 15", 1),
    ("AGE_15_64", "15–64", 2),
    ("AGE_65_PLUS", "65 and above", 3),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare():
    manifest = json.loads(
        (FOLDER / "manifest.json").read_text(encoding="utf-8-sig")
    )

    require(manifest["contract_version"] == CONTRACT,
            "Contract version mismatch")
    require(manifest["data_release_id"] == RELEASE,
            "Data release mismatch")
    require(manifest["validation_summary"]["error_count"] == 0,
            "Manifest contains validation errors")

    sources = {s["dataset_id"]: s for s in manifest["sources"]}
    require(len(sources) == len(manifest["sources"]) == 8,
            "Expected eight unique sources")
    require(set(sources) == {f"D{i:02}" for i in range(1, 9)},
            "Unexpected source identifiers")

    outputs = {o["filename"]: o for o in manifest["outputs"]}
    require(len(outputs) == len(manifest["outputs"]) == 8,
            "Expected eight unique outputs")
    require(set(outputs) == set(TABLES), "Unexpected output file list")

    # Check the original source files too.
    for source in sources.values():
        path = ROOT / "data" / "raw" / source["source_filename"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        require(digest == source["source_sha256"],
                f"Raw source hash mismatch: {path.name}")

    prepared = {}

    for filename, output in outputs.items():
        require(output["readiness"] in ("ready", "ready_with_warnings"),
                f"{filename}: output is not ready")
        require(output["rejected_count"] == 0,
                f"{filename}: rejected records exist")

        # Parse the exact bytes that were hashed.
        content = (FOLDER / filename).read_bytes()
        require(
            hashlib.sha256(content).hexdigest() == output["output_sha256"],
            f"{filename}: cleaned-file hash mismatch",
        )

        reader = csv.DictReader(
            io.StringIO(content.decode("utf-8-sig"), newline="")
        )
        rows = list(reader)
        headers = reader.fieldnames

        require(headers is not None and len(headers) == len(set(headers)),
                f"{filename}: invalid headers")
        require(len(rows) == output["row_count"],
                f"{filename}: row count mismatch")

        keys = set()

        for row in rows:
            require(None not in row and None not in row.values(),
                    f"{filename}: malformed CSV row")

            key = tuple(row[field] for field in output["logical_key"])
            require(key not in keys, f"{filename}: duplicate key {key}")
            keys.add(key)

            dataset_id = row["dataset_id"]
            require(dataset_id in output["source_ids"],
                    f"{filename}: unexpected source ID")
            source = sources[dataset_id]

            require(row["source_file_sha256"] == source["source_sha256"],
                    f"{filename}: source hash reference mismatch")

            for field, value in list(row.items()):
                if field == "count" and value == "":
                    row[field] = None
                elif field in INTEGER_FIELDS:
                    row[field] = int(value)
                elif field in DECIMAL_FIELDS:
                    number = Decimal(value)
                    require(number.is_finite(),
                            f"{filename}: non-finite {field}")
                    require(number == number.quantize(Decimal("0.01")),
                            f"{filename}: excessive precision in {field}")
                    row[field] = number

            require(
                1 <= row["source_row_number"] <= source["row_count"],
                f"{filename}: source row outside valid range",
            )

            if filename == "resale.csv":
                expected_id = (
                    f'D01:{row["source_file_sha256"]}:'
                    f'{row["source_row_number"]:09d}'
                )
                require(row["record_id"] == expected_id,
                        "Resale record ID does not match provenance")

            if filename == "mobility.csv":
                valid_count = (
                    row["count_status"] == "reported"
                    and row["count"] is not None
                    and row["count"] >= 0
                ) or (
                    row["count_status"] == "unresolved_dash"
                    and row["count"] is None
                )
                require(valid_count, "Invalid mobility count/status")

        prepared[filename] = (headers, rows)
        print(f"Validated {filename}: {len(rows):,} rows")

    print(
        "Source warnings retained:",
        manifest["validation_summary"]["warning_count"],
    )
    return manifest, prepared


def insert_rows(cursor, table, columns, rows):
    # Callers supply fixed table names and verified database column names.
    column_sql = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders})"

    for start in range(0, len(rows), 1000):
        cursor.executemany(
            sql,
            [tuple(row[column] for column in columns)
             for row in rows[start:start + 1000]],
        )


def main():
    manifest, prepared = prepare()
    password = getpass.getpass("hdb_dev password: ")

    connection = mariadb.connect(
        host="127.0.0.1",
        port=3306,
        user="hdb_dev",
        password=password,
        database="hdb_insights",
        autocommit=False,
    )

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SET SESSION sql_mode = "
            "'STRICT_ALL_TABLES,ERROR_FOR_DIVISION_BY_ZERO,"
            "NO_ENGINE_SUBSTITUTION'"
        )
        cursor.execute("SET SESSION foreign_key_checks = 1")
        cursor.execute("SET SESSION check_constraint_checks = 1")

        all_tables = [
            "source_dataset", "town", "flat_type",
            "ethnic_group", "age_group", "application_metadata",
            *TABLES.values(),
        ]

        # Check every target before inserting anything.
        for table in all_tables:
            cursor.execute(
                "SELECT ENGINE FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = ?",
                (table,),
            )
            require(cursor.fetchone() == ("InnoDB",),
                    f"{table}: missing table or not InnoDB")
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            require(cursor.fetchone()[0] == 0,
                    f"{table} is not empty. Initial load stopped.")

        # Validate CSV columns against the actual table columns.
        for filename, (headers, rows) in prepared.items():
            table = TABLES[filename]
            cursor.execute(f"SHOW COLUMNS FROM `{table}`")
            database_columns = {row[0] for row in cursor.fetchall()}
            expected_columns = set(headers)
            if filename == "resale.csv":
                expected_columns.remove("town_name")
                expected_columns.add("town_id")
            require(expected_columns == database_columns,
                    f"{filename}: CSV/table column mismatch")

        cursor.executemany(
            "INSERT INTO source_dataset "
            "(dataset_id, source_filename, source_file_sha256, "
            "source_row_count) VALUES (?, ?, ?, ?)",
            [
                (s["dataset_id"], s["source_filename"],
                 s["source_sha256"], s["row_count"])
                for s in manifest["sources"]
            ],
        )

        cursor.executemany(
            "INSERT INTO flat_type VALUES (?, ?, ?)",
            [(code, label, int(code == "ALL"))
             for code, label in FLATS.items()],
        )
        cursor.executemany(
            "INSERT INTO ethnic_group VALUES (?, ?, ?)",
            [(code, label, int(code == "ALL"))
             for code, label in ETHNICITIES.items()],
        )
        cursor.executemany(
            "INSERT INTO age_group VALUES (?, ?, ?)", AGES
        )

        towns = sorted({
            row["town_name"] for row in prepared["resale.csv"][1]
        })
        cursor.executemany(
            "INSERT INTO town (town_name) VALUES (?)",
            [(name,) for name in towns],
        )
        cursor.execute("SELECT town_name, town_id FROM town")
        town_ids = dict(cursor.fetchall())

        for filename, (headers, rows) in prepared.items():
            columns = list(headers)

            if filename == "resale.csv":
                columns[columns.index("town_name")] = "town_id"
                rows = [
                    {**row, "town_id": town_ids[row["town_name"]]}
                    for row in rows
                ]

            table = TABLES[filename]
            insert_rows(cursor, table, columns, rows)
            cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
            actual = cursor.fetchone()[0]
            require(actual == len(rows), f"{table}: load count mismatch")
            print(f"Loaded {table}: {actual:,} rows (not yet committed)")

        expected_nulls = sum(
            row["count"] is None for row in prepared["mobility.csv"][1]
        )
        cursor.execute(
            "SELECT COUNT(*) FROM mobility_observation "
            "WHERE count IS NULL AND count_status = 'unresolved_dash'"
        )
        require(cursor.fetchone()[0] == expected_nulls,
                "Mobility null count mismatch")

        # Publish the release only after all preceding checks succeed.
        cursor.execute(
            "INSERT INTO application_metadata "
            "(metadata_id, contract_version, data_release_id, loaded_at_utc) "
            "VALUES (1, ?, ?, ?)",
            (
                CONTRACT,
                RELEASE,
                datetime.now(timezone.utc).replace(tzinfo=None),
            ),
        )

        connection.commit()
        print(f"\nSUCCESS: committed release {RELEASE}")
        print(f"Preserved {expected_nulls} unresolved mobility counts.")

    except Exception:
        connection.rollback()
        print("\nFAILED: transaction rolled back. No load committed.")
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()