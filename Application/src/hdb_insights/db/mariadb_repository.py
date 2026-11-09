import logging
import re
from decimal import Decimal, ROUND_HALF_UP

import mariadb

from .mariadb_connection import get_connection


CONTRACT_VERSION = "HDBI-1.0.0"
LOGGER = logging.getLogger(__name__)

FROM_SQL = """
    FROM resale_transaction AS r
    JOIN town AS t ON t.town_id = r.town_id
"""


class ValidationError(ValueError):
    pass


class DataNotReadyError(Exception):
    pass


def _response(meta, data=None, code=None, message=None):
    return {
        "ok": code is None,
        "data": data if code is None else None,
        "error": None if code is None else {
            "code": code,
            "message": message,
        },
        "meta": meta,
    }


def _serialise(value):
    if isinstance(value, Decimal):
        return format(
            value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            ".2f",
        )
    if isinstance(value, dict):
        return {key: _serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    return value


def _validate_filters(filters):
    if filters is None:
        return {}

    if not isinstance(filters, dict):
        raise ValidationError("filters must be a dictionary.")

    allowed = {"town_name", "flat_type_code", "start_month", "end_month"}
    if set(filters) - allowed:
        raise ValidationError("Unknown resale filter.")

    for name, value in filters.items():
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(
                    f"{name} must be a non-empty string."
                )

    for name in ("start_month", "end_month"):
        value = filters.get(name)
        if value is not None:
            if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
                raise ValidationError(f"{name} must use YYYY-MM.")
            if value.startswith("0000"):
                raise ValidationError(f"{name} must have a valid year.")

    start = filters.get("start_month")
    end = filters.get("end_month")
    if start is not None and end is not None and start > end:
        raise ValidationError("start_month must not exceed end_month.")

    return dict(filters)


def _where_clause(cursor, filters):
    town = filters.get("town_name")
    if town is not None:
        cursor.execute(
            "SELECT town_id FROM town WHERE town_name = ?",
            (town,),
        )
        if cursor.fetchone() is None:
            raise ValidationError("Unknown town_name.")

    flat_type = filters.get("flat_type_code")
    if flat_type is not None:
        cursor.execute(
            """
            SELECT flat_type_code
            FROM flat_type
            WHERE flat_type_code = ?
              AND flat_type_code <> 'ALL'
            """,
            (flat_type,),
        )
        if cursor.fetchone() is None:
            raise ValidationError(
                "Unknown or invalid resale flat_type_code."
            )

    conditions = (
        ("town_name", "t.town_name = ?"),
        ("flat_type_code", "r.flat_type_code = ?"),
        ("start_month", "r.registration_month >= ?"),
        ("end_month", "r.registration_month <= ?"),
    )

    clauses = []
    parameters = []

    for name, condition in conditions:
        value = filters.get(name)
        if value is not None:
            clauses.append(condition)
            parameters.append(value)

    return (
        " AND ".join(clauses) if clauses else "1 = 1",
        tuple(parameters),
    )


def _run_resale(operation, filters, limit=50, offset=0):
    meta = {
        "backend": "mariadb",
        "contract_version": CONTRACT_VERSION,
        "data_release_id": None,
    }
    connection = None

    try:
        filters = _validate_filters(filters)

        if operation == "search":
            if type(limit) is not int or not 1 <= limit <= 500:
                raise ValidationError(
                    "limit must be an integer from 1 to 500."
                )
            if type(offset) is not int or offset < 0:
                raise ValidationError(
                    "offset must be a non-negative integer."
                )

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # Count, page and metadata reads use one consistent snapshot.
        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
        )
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")

        cursor.execute(
            """
            SELECT contract_version, data_release_id
            FROM application_metadata
            WHERE metadata_id = 1
            """
        )
        metadata = cursor.fetchone()

        if (
            metadata is None
            or metadata["contract_version"] != CONTRACT_VERSION
            or not metadata["data_release_id"]
        ):
            raise DataNotReadyError()

        meta["data_release_id"] = metadata["data_release_id"]
        where_sql, parameters = _where_clause(cursor, filters)

        if operation == "search":
            cursor.execute(
                f"""
                SELECT COUNT(*) AS total_count
                {FROM_SQL}
                WHERE {where_sql}
                """,
                parameters,
            )
            total_count = cursor.fetchone()["total_count"]

            cursor.execute(
                f"""
                SELECT
                    r.record_id,
                    r.registration_month,
                    t.town_name,
                    r.flat_type_code,
                    r.block,
                    r.street_name,
                    r.storey_lower,
                    r.storey_upper,
                    r.floor_area_sqm,
                    r.flat_model,
                    r.lease_commence_year,
                    r.remaining_lease_months,
                    r.resale_price
                {FROM_SQL}
                WHERE {where_sql}
                ORDER BY r.registration_month, r.record_id
                LIMIT ? OFFSET ?
                """,
                parameters + (limit, offset),
            )
            data = {
                "rows": cursor.fetchall(),
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
            }

        elif operation == "summary":
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS transaction_count,
                    ROUND(AVG(r.resale_price), 2) AS average_price,
                    ROUND(
                        AVG(r.resale_price / r.floor_area_sqm), 2
                    ) AS average_price_per_sqm
                {FROM_SQL}
                WHERE {where_sql}
                """,
                parameters,
            )
            data = cursor.fetchone()

        elif operation == "trend":
            cursor.execute(
                f"""
                SELECT
                    r.registration_month,
                    COUNT(*) AS transaction_count,
                    ROUND(AVG(r.resale_price), 2) AS average_price,
                    ROUND(
                        AVG(r.resale_price / r.floor_area_sqm), 2
                    ) AS average_price_per_sqm
                {FROM_SQL}
                WHERE {where_sql}
                GROUP BY r.registration_month
                ORDER BY r.registration_month
                """,
                parameters,
            )
            data = {"rows": cursor.fetchall()}

        else:
            raise RuntimeError("Unknown internal operation.")

        cursor.close()
        return _response(meta, data=_serialise(data))

    except ValidationError as error:
        return _response(
            meta, code="VALIDATION_ERROR", message=str(error)
        )

    except DataNotReadyError:
        return _response(
            meta,
            code="DATA_NOT_READY",
            message="A compatible data release has not been loaded.",
        )

    except mariadb.Error as error:
        LOGGER.error("MariaDB operation failed; errno=%s", error.errno)
        unavailable = error.errno in {
            1040, 1042, 1045, 2002, 2003, 2006, 2013
        }
        return _response(
            meta,
            code="DB_UNAVAILABLE" if unavailable else "INTERNAL_ERROR",
            message=(
                "Unable to communicate with MariaDB."
                if unavailable
                else "The database query could not be completed."
            ),
        )

    except Exception as error:
        # Log the exception type without exposing credentials.
        LOGGER.error("Adapter failure: %s", type(error).__name__)
        return _response(
            meta,
            code="INTERNAL_ERROR",
            message="Check application configuration and adapter setup.",
        )

    finally:
        if connection is not None:
            connection.close()


def search_resale(filters, limit=50, offset=0):
    return _run_resale("search", filters, limit, offset)


def summarise_resale(filters):
    return _run_resale("summary", filters)


def resale_trend(filters):
    return _run_resale("trend", filters)


def demographic_profile(group_type, group_code, survey_year):
    """F02: Read one demographic profile with source lineage."""

    meta = {
        "backend": "mariadb",
        "contract_version": CONTRACT_VERSION,
        "data_release_id": None,
    }
    connection = None
    cursor = None

    def success(data):
        return {
            "ok": True,
            "data": _serialise(data),
            "error": None,
            "meta": meta,
        }

    def failure(code, message):
        return {
            "ok": False,
            "data": None,
            "error": {"code": code, "message": message},
            "meta": meta,
        }

    # SQL identifiers come only from this fixed mapping.
    # User-supplied values are passed separately as parameters.
    dimensions = {
        "flat_type": {
            "lookup": "flat_type",
            "column": "flat_type_code",
            "stats": "age_stats_by_flat_type",
            "ages": "age_by_flat_type",
            "population": "population_15_plus_by_flat_type",
        },
        "ethnicity": {
            "lookup": "ethnic_group",
            "column": "ethnic_group_code",
            "stats": "age_stats_by_ethnicity",
            "ages": "age_by_ethnicity",
            "population": "population_15_plus_by_ethnicity",
        },
    }

    try:
        if (
            not isinstance(group_type, str)
            or group_type not in dimensions
        ):
            return failure(
                "VALIDATION_ERROR",
                "group_type must be 'flat_type' or 'ethnicity'.",
            )

        if not isinstance(group_code, str) or not group_code.strip():
            return failure(
                "VALIDATION_ERROR",
                "group_code must be a non-empty string.",
            )

        if type(survey_year) is not int or not 1 <= survey_year <= 9999:
            return failure(
                "VALIDATION_ERROR",
                "survey_year must be an integer from 1 to 9999.",
            )

        spec = dimensions[group_type]
        column = spec["column"]

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        # All profile components must come from the same DB snapshot.
        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
        )
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")

        cursor.execute("""
            SELECT contract_version, data_release_id
            FROM application_metadata
            WHERE metadata_id = 1
        """)
        metadata = cursor.fetchone()

        if (
            metadata is None
            or metadata["contract_version"] != CONTRACT_VERSION
            or not metadata["data_release_id"]
        ):
            return failure(
                "DATA_NOT_READY",
                "The expected analytical data contract is not loaded.",
            )

        meta["data_release_id"] = metadata["data_release_id"]

        cursor.execute(
            f"""
            SELECT {column}
            FROM {spec["lookup"]}
            WHERE {column} = ?
            """,
            (group_code,),
        )

        if cursor.fetchone() is None:
            return failure(
                "VALIDATION_ERROR",
                "Unknown group_code for the selected group_type.",
            )

        parameters = (group_code, survey_year)

        # Read statistics, distribution and population separately.
        # This avoids multiplying population across three age rows.
        cursor.execute(
            f"""
            SELECT average_age, median_age,
                   dataset_id, source_file_sha256, source_row_number
            FROM {spec["stats"]}
            WHERE {column} = ? AND survey_year = ?
            """,
            parameters,
        )
        statistics = cursor.fetchone()

        cursor.execute(
            f"""
            SELECT a.age_group_code, a.percentage,
                   a.dataset_id, a.source_file_sha256,
                   a.source_row_number
            FROM {spec["ages"]} AS a
            JOIN age_group AS g
                ON g.age_group_code = a.age_group_code
            WHERE a.{column} = ? AND a.survey_year = ?
            ORDER BY g.sort_order
            """,
            parameters,
        )
        age_rows = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT population_15_plus,
                   dataset_id, source_file_sha256, source_row_number
            FROM {spec["population"]}
            WHERE {column} = ? AND survey_year = ?
            """,
            parameters,
        )
        population = cursor.fetchone()

        if statistics is None and not age_rows and population is None:
            meta["note"] = (
                "No demographic profile is available for "
                "this group and survey year."
            )
            return success(None)

        expected_age_groups = [
            "BELOW_15",
            "AGE_15_64",
            "AGE_65_PLUS",
        ]

        if (
            statistics is None
            or [row["age_group_code"] for row in age_rows]
            != expected_age_groups
        ):
            return failure(
                "DATA_NOT_READY",
                "The demographic profile is incomplete.",
            )

        # ALL has no population row in the approved prepared release.
        # Preserve that absence rather than calculating a replacement.
        if population is None and group_code != "ALL":
            return failure(
                "DATA_NOT_READY",
                "The demographic population component is missing.",
            )

        contributing_rows = [statistics, *age_rows]
        if population is not None:
            contributing_rows.append(population)

        source_keys = {
            (
                row["dataset_id"],
                row["source_file_sha256"],
                row["source_row_number"],
            )
            for row in contributing_rows
        }

        source_rows = [
            {
                "dataset_id": dataset_id,
                "source_file_sha256": source_hash,
                "source_row_number": row_number,
            }
            for dataset_id, source_hash, row_number in sorted(
                source_keys,
                key=lambda item: (item[0], item[2], item[1]),
            )
        ]

        profile = {
            "group_type": group_type,
            "group_code": group_code,
            "survey_year": survey_year,
            "average_age": statistics["average_age"],
            "median_age": statistics["median_age"],
            "population_15_plus": (
                population["population_15_plus"]
                if population is not None
                else None
            ),
            "population_status": (
                "reported" if population is not None else "not_provided"
            ),
            "age_distribution": [
                {
                    "age_group_code": row["age_group_code"],
                    "percentage": row["percentage"],
                }
                for row in age_rows
            ],
            "source_rows": source_rows,
        }
        return success(profile)

    except mariadb.Error as exc:
        LOGGER.error(
            "demographic_profile database error: errno=%s",
            exc.errno,
        )
        unavailable = {
            1040, 1042, 1045, 2002, 2003, 2006, 2013,
        }
        if exc.errno in unavailable:
            return failure(
                "DB_UNAVAILABLE",
                "The database connection is unavailable.",
            )
        return failure(
            "INTERNAL_ERROR",
            "The demographic query could not be completed.",
        )

    except Exception as exc:
        LOGGER.error(
            "demographic_profile failed: %s",
            type(exc).__name__,
        )
        return failure(
            "INTERNAL_ERROR",
            "The demographic operation could not be completed.",
        )

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def mobility_breakdown(
    workplace_area,
    residence_region_code,
    survey_year=2020,
):
    """F03: Transport shares using the published ALL-mode total."""

    meta = {
        "backend": "mariadb",
        "contract_version": CONTRACT_VERSION,
        "data_release_id": None,
    }
    connection = None
    cursor = None

    def success(data):
        return {
            "ok": True,
            "data": _serialise(data),
            "error": None,
            "meta": meta,
        }

    def failure(code, message):
        return {
            "ok": False,
            "data": None,
            "error": {"code": code, "message": message},
            "meta": meta,
        }

    regions = {
        "ALL", "CENTRAL", "EAST",
        "NORTH", "NORTH_EAST", "WEST",
    }
    expected_modes = [
        "RAIL_BUS",
        "CAR_TAXI_PRIVATE_HIRE",
        "OTHER",
        "NO_TRANSPORT",
    ]

    try:
        if not isinstance(workplace_area, str) or not workplace_area.strip():
            return failure(
                "VALIDATION_ERROR",
                "workplace_area must be a non-empty string.",
            )

        if (
            not isinstance(residence_region_code, str)
            or residence_region_code not in regions
        ):
            return failure(
                "VALIDATION_ERROR",
                "Unknown residence_region_code.",
            )

        if type(survey_year) is not int or not 1 <= survey_year <= 9999:
            return failure(
                "VALIDATION_ERROR",
                "survey_year must be an integer from 1 to 9999.",
            )

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
        )
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")

        cursor.execute("""
            SELECT contract_version, data_release_id
            FROM application_metadata
            WHERE metadata_id = 1
        """)
        metadata = cursor.fetchone()

        if (
            metadata is None
            or metadata["contract_version"] != CONTRACT_VERSION
            or not metadata["data_release_id"]
        ):
            return failure(
                "DATA_NOT_READY",
                "The expected analytical data contract is not loaded.",
            )

        meta["data_release_id"] = metadata["data_release_id"]

        cursor.execute(
            """
            SELECT workplace_area
            FROM mobility_observation
            WHERE workplace_area = ?
            LIMIT 1
            """,
            (workplace_area,),
        )

        if cursor.fetchone() is None:
            return failure(
                "VALIDATION_ERROR",
                "Unknown workplace_area.",
            )

        parameters = (
            workplace_area,
            residence_region_code,
            survey_year,
        )

        cursor.execute(
            """
            SELECT count, count_status
            FROM mobility_observation
            WHERE workplace_area = ?
              AND residence_region_code = ?
              AND survey_year = ?
              AND transport_mode_code = 'ALL'
            """,
            parameters,
        )
        total = cursor.fetchone()

        # Calculate shares in MariaDB, using the existing SQL logic.
        cursor.execute(
            """
            SELECT
                m.transport_mode_code,
                m.count,
                m.count_status,
                ROUND(
                    m.count * 100.00 / NULLIF(totals.count, 0),
                    2
                ) AS share_pct
            FROM mobility_observation AS m
            LEFT JOIN mobility_observation AS totals
                ON totals.survey_year = m.survey_year
                AND totals.workplace_area = m.workplace_area
                AND totals.residence_region_code =
                    m.residence_region_code
                AND totals.transport_mode_code = 'ALL'
            WHERE m.workplace_area = ?
              AND m.residence_region_code = ?
              AND m.survey_year = ?
              AND m.transport_mode_code <> 'ALL'
            ORDER BY CASE m.transport_mode_code
                WHEN 'RAIL_BUS' THEN 1
                WHEN 'CAR_TAXI_PRIVATE_HIRE' THEN 2
                WHEN 'OTHER' THEN 3
                WHEN 'NO_TRANSPORT' THEN 4
            END
            """,
            parameters,
        )
        rows = cursor.fetchall()

        if total is None or [
            row["transport_mode_code"] for row in rows
        ] != expected_modes:
            return failure(
                "DATA_NOT_READY",
                "A complete mobility breakdown is not available "
                "for the selected workplace, region and year.",
            )

        # Reject inconsistent stored statuses rather than hiding them.
        for observation in [total, *rows]:
            count = observation["count"]
            status = observation["count_status"]

            valid = (
                status == "reported"
                and type(count) is int
                and count >= 0
            ) or (
                status == "unresolved_dash"
                and count is None
            )

            if not valid:
                return failure(
                    "DATA_NOT_READY",
                    "Mobility count and status are inconsistent.",
                )

        note = (
            "Shares use the published ALL-mode total for the selected "
            "workplace, region and year. Unresolved counts remain null. "
            "Published counts and rounded shares may not add exactly "
            "to the total or to 100%; values are not normalised."
        )

        if total["count"] is None:
            note += " The published total is unresolved; all shares are null."
        elif total["count"] == 0:
            note += " The published total is zero; all shares are null."

        return success({
            "rows": rows,
            "published_total": total["count"],
            "note": note,
        })

    except mariadb.Error as exc:
        LOGGER.error(
            "mobility_breakdown database error: errno=%s",
            exc.errno,
        )
        if exc.errno in {1040, 1042, 1045, 2002, 2003, 2006, 2013}:
            return failure(
                "DB_UNAVAILABLE",
                "The database connection is unavailable.",
            )
        return failure(
            "INTERNAL_ERROR",
            "The mobility query could not be completed.",
        )

    except Exception as exc:
        LOGGER.error(
            "mobility_breakdown failed: %s",
            type(exc).__name__,
        )
        return failure(
            "INTERNAL_ERROR",
            "The mobility operation could not be completed.",
        )

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()

def list_filter_options(domain):
    """Database-backed dropdown options.

    Proposed C05 detail: agree these nested option keys with B/C/D
    before integrating the shared UI.
    """
    meta = {
        "backend": "mariadb",
        "contract_version": CONTRACT_VERSION,
        "data_release_id": None,
    }
    connection = None

    try:
        if (
            not isinstance(domain, str)
            or domain not in {"resale", "demographic", "mobility"}
        ):
            raise ValidationError(
                "domain must be resale, demographic or mobility."
            )

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
        )
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")

        cursor.execute("""
            SELECT contract_version, data_release_id
            FROM application_metadata
            WHERE metadata_id = 1
        """)
        metadata = cursor.fetchone()

        if (
            metadata is None
            or metadata["contract_version"] != CONTRACT_VERSION
            or not metadata["data_release_id"]
        ):
            raise DataNotReadyError()

        meta["data_release_id"] = metadata["data_release_id"]

        if domain == "resale":
            cursor.execute("""
                SELECT t.town_name
                FROM town AS t
                WHERE EXISTS (
                    SELECT 1
                    FROM resale_transaction AS r
                    WHERE r.town_id = t.town_id
                )
                ORDER BY t.town_name
            """)
            towns = [row["town_name"] for row in cursor.fetchall()]

            cursor.execute("""
                SELECT f.flat_type_code, f.display_label
                FROM flat_type AS f
                WHERE f.flat_type_code <> 'ALL'
                  AND EXISTS (
                      SELECT 1
                      FROM resale_transaction AS r
                      WHERE r.flat_type_code = f.flat_type_code
                  )
                ORDER BY f.flat_type_code
            """)
            flat_types = cursor.fetchall()

            cursor.execute("""
                SELECT DISTINCT registration_month
                FROM resale_transaction
                ORDER BY registration_month
            """)
            months = [
                row["registration_month"] for row in cursor.fetchall()
            ]

            options = {
                "town_names": towns,
                "flat_types": flat_types,
                "registration_months": months,
            }

        elif domain == "demographic":
            cursor.execute("""
                SELECT
                    'flat_type' AS group_type,
                    s.flat_type_code AS group_code,
                    f.display_label,
                    s.survey_year
                FROM age_stats_by_flat_type AS s
                JOIN flat_type AS f
                    ON f.flat_type_code = s.flat_type_code

                UNION ALL

                SELECT
                    'ethnicity' AS group_type,
                    s.ethnic_group_code AS group_code,
                    e.display_label,
                    s.survey_year
                FROM age_stats_by_ethnicity AS s
                JOIN ethnic_group AS e
                    ON e.ethnic_group_code = s.ethnic_group_code

                ORDER BY group_type, group_code, survey_year
            """)
            options = {"profiles": cursor.fetchall()}

        else:
            cursor.execute("""
                SELECT DISTINCT
                    workplace_area,
                    residence_region_code,
                    survey_year
                FROM mobility_observation
                ORDER BY workplace_area, residence_region_code, survey_year
            """)
            options = {"selections": cursor.fetchall()}

        cursor.close()
        return _response(meta, data={"options": _serialise(options)})

    except ValidationError as error:
        return _response(
            meta, code="VALIDATION_ERROR", message=str(error)
        )

    except DataNotReadyError:
        return _response(
            meta,
            code="DATA_NOT_READY",
            message="A compatible data release has not been loaded.",
        )

    except mariadb.Error as error:
        LOGGER.error(
            "Filter options query failed; errno=%s", error.errno
        )
        unavailable = error.errno in {
            1040, 1042, 1045, 2002, 2003, 2006, 2013
        }
        return _response(
            meta,
            code="DB_UNAVAILABLE" if unavailable else "INTERNAL_ERROR",
            message=(
                "Unable to communicate with MariaDB."
                if unavailable
                else "Filter options could not be retrieved."
            ),
        )

    except Exception as error:
        LOGGER.error(
            "Filter options failure: %s", type(error).__name__
        )
        return _response(
            meta,
            code="INTERNAL_ERROR",
            message="Check application configuration and adapter setup.",
        )

    finally:
        if connection is not None:
            connection.close()

def _validate_demo_record_id(demo_record_id):
    if (
        not isinstance(demo_record_id, str)
        or re.fullmatch(
            r"demo:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
            r"-[0-9a-f]{4}-[0-9a-f]{12}",
            demo_record_id,
        ) is None
    ):
        raise ValidationError(
            "demo_record_id must use the format demo:<lowercase UUID>."
        )


def _read_demo_row(cursor, demo_record_id):
    """Internal helper reused by Read, Create and Update."""
    cursor.execute(
        """
        SELECT
            d.demo_record_id,
            d.record_kind,
            d.seed_record_id,
            d.base_data_release_id,
            d.registration_month,
            t.town_name,
            d.flat_type_code,
            d.block,
            d.street_name,
            d.storey_lower,
            d.storey_upper,
            d.floor_area_sqm,
            d.flat_model,
            d.lease_commence_year,
            d.remaining_lease_months,
            d.resale_price
        FROM hdb_insights_demo.demo_resale_transaction AS d
        JOIN hdb_insights_demo.town AS t
            ON t.town_id = d.town_id
        WHERE d.demo_record_id = ?
        """,
        (demo_record_id,),
    )
    return cursor.fetchone()


def get_demo_resale(demo_record_id):
    """CAP01: Read a demo record without changing either database."""
    meta = {
        "backend": "mariadb",
        "contract_version": CONTRACT_VERSION,
        "data_release_id": None,
        "dataset_kind": "demo",
        "base_data_release_id": None,
    }
    connection = None

    try:
        _validate_demo_record_id(demo_record_id)

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
        )
        cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")

        cursor.execute("""
            SELECT contract_version, data_release_id
            FROM hdb_insights.application_metadata
            WHERE metadata_id = 1
        """)
        metadata = cursor.fetchone()

        if (
            metadata is None
            or metadata["contract_version"] != CONTRACT_VERSION
            or not metadata["data_release_id"]
        ):
            raise DataNotReadyError()

        active_release = metadata["data_release_id"]
        meta["data_release_id"] = active_release

        record = _read_demo_row(cursor, demo_record_id)
        cursor.close()

        if record is None:
            return _response(
                meta,
                code="NOT_FOUND",
                message="The requested demo record does not exist.",
            )

        meta["base_data_release_id"] = record["base_data_release_id"]

        if record["base_data_release_id"] != active_release:
            return _response(
                meta,
                code="DATA_NOT_READY",
                message=(
                    "This demo record belongs to a different data release."
                ),
            )

        return _response(meta, data=_serialise(record))

    except ValidationError as error:
        return _response(
            meta, code="VALIDATION_ERROR", message=str(error)
        )

    except DataNotReadyError:
        return _response(
            meta,
            code="DATA_NOT_READY",
            message="A compatible analytical release has not been loaded.",
        )

    except mariadb.Error as error:
        LOGGER.error("Demo read failed; errno=%s", error.errno)
        unavailable = error.errno in {
            1040, 1042, 1045, 2002, 2003, 2006, 2013
        }
        return _response(
            meta,
            code="DB_UNAVAILABLE" if unavailable else "INTERNAL_ERROR",
            message=(
                "Unable to communicate with MariaDB."
                if unavailable
                else "The demo record could not be retrieved."
            ),
        )

    except Exception as error:
        LOGGER.error("Demo read failure: %s", type(error).__name__)
        return _response(
            meta,
            code="INTERNAL_ERROR",
            message="Check application configuration and adapter setup.",
        )

    finally:
        if connection is not None:
            connection.close()


DEMO_BUSINESS_FIELDS = {
    "registration_month",
    "town_name",
    "flat_type_code",
    "block",
    "street_name",
    "storey_lower",
    "storey_upper",
    "floor_area_sqm",
    "flat_model",
    "lease_commence_year",
    "remaining_lease_months",
    "resale_price",
}


def _validate_demo_business(values):
    """Validate a complete set of demo business fields."""
    if not isinstance(values, dict) or set(values) != DEMO_BUSINESS_FIELDS:
        raise ValidationError(
            "Provide exactly the twelve required resale business fields."
        )

    cleaned = dict(values)

    text_limits = {
        "town_name": 100,
        "flat_type_code": 20,
        "block": 20,
        "street_name": 100,
        "flat_model": 100,
    }

    for field, maximum in text_limits.items():
        value = cleaned[field]
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > maximum
        ):
            raise ValidationError(
                f"{field} must contain 1 to {maximum} characters."
            )

    month = cleaned["registration_month"]
    if (
        not isinstance(month, str)
        or re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month) is None
        or month.startswith("0000")
    ):
        raise ValidationError(
            "registration_month must be a valid YYYY-MM."
        )

    if cleaned["flat_type_code"] == "ALL":
        raise ValidationError("ALL is not a transaction flat type.")

    integer_limits = {
        "storey_lower": (1, 65535),
        "storey_upper": (1, 65535),
        "lease_commence_year": (1, 9999),
        "remaining_lease_months": (0, 65535),
    }

    for field, (minimum, maximum) in integer_limits.items():
        value = cleaned[field]
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValidationError(
                f"{field} must be an integer from {minimum} to {maximum}."
            )

    if cleaned["storey_upper"] < cleaned["storey_lower"]:
        raise ValidationError(
            "storey_upper must be at least storey_lower."
        )

    for field, maximum in (
        ("floor_area_sqm", Decimal("999999.99")),
        ("resale_price", Decimal("999999999999.99")),
    ):
        value = cleaned[field]

        if not (
            isinstance(value, (str, Decimal))
            or type(value) is int
        ):
            raise ValidationError(
                f"{field} must be a decimal string, Decimal or integer."
            )

        try:
            number = Decimal(value)
        except (ValueError, ArithmeticError):
            raise ValidationError(f"{field} must be a valid decimal.")

        if not number.is_finite() or not Decimal("0") < number <= maximum:
            raise ValidationError(
                f"{field} must be positive and within the database range."
            )

        rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if number != rounded:
            raise ValidationError(
                f"{field} must have no more than two decimal places."
            )

        cleaned[field] = rounded

    return cleaned


def create_demo_resale(payload):
    """CAP01: Create and commit a demo record from a registered seed."""
    from uuid import uuid4

    meta = {
        "backend": "mariadb",
        "contract_version": CONTRACT_VERSION,
        "data_release_id": None,
        "dataset_kind": "demo",
        "base_data_release_id": None,
    }
    connection = None

    try:
        required = DEMO_BUSINESS_FIELDS | {"seed_record_id"}
        if not isinstance(payload, dict) or set(payload) != required:
            raise ValidationError(
                "Provide seed_record_id and the twelve business fields; "
                "identity and provenance fields are generated internally."
            )

        seed_id = payload["seed_record_id"]
        if (
            not isinstance(seed_id, str)
            or not seed_id.strip()
            or len(seed_id) > 96
        ):
            raise ValidationError("Invalid seed_record_id.")

        values = _validate_demo_business({
            field: payload[field] for field in DEMO_BUSINESS_FIELDS
        })

        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("START TRANSACTION")

        # Keep the active release stable during this write.
        cursor.execute("""
            SELECT contract_version, data_release_id
            FROM hdb_insights.application_metadata
            WHERE metadata_id = 1
            LOCK IN SHARE MODE
        """)
        metadata = cursor.fetchone()

        if (
            metadata is None
            or metadata["contract_version"] != CONTRACT_VERSION
            or not metadata["data_release_id"]
        ):
            raise DataNotReadyError()

        release = metadata["data_release_id"]
        meta["data_release_id"] = release
        meta["base_data_release_id"] = release

        cursor.execute(
            """
            SELECT dataset_id, source_file_sha256, source_row_number
            FROM hdb_insights.resale_transaction
            WHERE record_id = ?
            """,
            (seed_id,),
        )
        source = cursor.fetchone()

        if source is None:
            raise ValidationError(
                "seed_record_id does not identify an analytical resale record."
            )

        cursor.execute(
            """
            SELECT dataset_id, source_file_sha256, source_row_number
            FROM hdb_insights_demo.demo_seed
            WHERE seed_record_id = ? AND base_data_release_id = ?
            """,
            (seed_id, release),
        )
        seed = cursor.fetchone()

        if seed is None or seed != source:
            return _response(
                meta,
                code="DATA_NOT_READY",
                message=(
                    "This source record has not been registered as a "
                    "matching demo seed for the active release."
                ),
            )

        cursor.execute(
            """
            SELECT town_id
            FROM hdb_insights_demo.town
            WHERE town_name = ?
            """,
            (values["town_name"],),
        )
        town = cursor.fetchone()
        if town is None:
            raise ValidationError("Unknown demo town_name.")

        cursor.execute(
            """
            SELECT flat_type_code
            FROM hdb_insights_demo.flat_type
            WHERE flat_type_code = ? AND flat_type_code <> 'ALL'
            """,
            (values["flat_type_code"],),
        )
        if cursor.fetchone() is None:
            raise ValidationError("Unknown demo flat_type_code.")

        demo_id = f"demo:{uuid4()}"

        cursor.execute(
            """
            INSERT INTO hdb_insights_demo.demo_resale_transaction (
                demo_record_id, record_kind,
                seed_record_id, base_data_release_id,
                registration_month, town_id, flat_type_code,
                block, street_name, storey_lower, storey_upper,
                floor_area_sqm, flat_model, lease_commence_year,
                remaining_lease_months, resale_price
            )
            VALUES (?, 'demo', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                demo_id, seed_id, release,
                values["registration_month"],
                town["town_id"],
                values["flat_type_code"],
                values["block"],
                values["street_name"],
                values["storey_lower"],
                values["storey_upper"],
                values["floor_area_sqm"],
                values["flat_model"],
                values["lease_commence_year"],
                values["remaining_lease_months"],
                values["resale_price"],
            ),
        )

        record = _read_demo_row(cursor, demo_id)
        if record is None:
            raise RuntimeError("Inserted demo record could not be read.")

        # Prepare the response before committing.
        result = _response(meta, data=_serialise(record))
        cursor.close()
        connection.commit()
        return result

    except ValidationError as error:
        return _response(
            meta, code="VALIDATION_ERROR", message=str(error)
        )

    except DataNotReadyError:
        return _response(
            meta,
            code="DATA_NOT_READY",
            message="A compatible analytical release has not been loaded.",
        )

    except mariadb.Error as error:
        LOGGER.error("Demo create failed; errno=%s", error.errno)
        if error.errno == 1062:
            code = "CONFLICT"
        elif error.errno in {1040, 1042, 1045, 2002, 2003, 2006, 2013}:
            code = "DB_UNAVAILABLE"
        else:
            code = "INTERNAL_ERROR"

        return _response(
            meta,
            code=code,
            message="The demo creation could not be confirmed.",
        )

    except Exception as error:
        LOGGER.error("Demo create failure: %s", type(error).__name__)
        return _response(
            meta,
            code="INTERNAL_ERROR",
            message="The demo creation could not be completed.",
        )

    finally:
        if connection is not None:
            # Closing rolls back any transaction that did not commit.
            connection.close()

def _modify_demo_resale(operation, demo_record_id, changes=None):
    """Update or delete one locked demo record in a transaction."""
    meta = {
        "backend": "mariadb", "contract_version": CONTRACT_VERSION,
        "data_release_id": None, "dataset_kind": "demo",
        "base_data_release_id": None,
    }
    connection = None
    try:
        _validate_demo_record_id(demo_record_id)
        if operation not in {"update", "delete"}:
            raise RuntimeError("Unknown demo operation.")
        if operation == "update":
            if not isinstance(changes, dict) or not changes:
                raise ValidationError("changes must be a non-empty dictionary.")
            if set(changes) - DEMO_BUSINESS_FIELDS:
                raise ValidationError(
                    "Only resale business fields can be updated; "
                    "identity and lineage cannot be changed."
                )
        connection = get_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("START TRANSACTION")
        cursor.execute("""
            SELECT contract_version, data_release_id
            FROM hdb_insights.application_metadata
            WHERE metadata_id = 1
            LOCK IN SHARE MODE
        """)
        metadata = cursor.fetchone()
        if (metadata is None
                or metadata["contract_version"] != CONTRACT_VERSION
                or not metadata["data_release_id"]):
            raise DataNotReadyError()
        active_release = metadata["data_release_id"]
        meta["data_release_id"] = active_release
        cursor.execute("""
            SELECT base_data_release_id
            FROM hdb_insights_demo.demo_resale_transaction
            WHERE demo_record_id = ? FOR UPDATE
        """, (demo_record_id,))
        locked = cursor.fetchone()
        if locked is None:
            return _response(meta, code="NOT_FOUND",
                             message="The requested demo record does not exist.")
        meta["base_data_release_id"] = locked["base_data_release_id"]
        if locked["base_data_release_id"] != active_release:
            return _response(meta, code="DATA_NOT_READY",
                             message="This demo record belongs to a different release.")
        if operation == "delete":
            cursor.execute("""
                DELETE FROM hdb_insights_demo.demo_resale_transaction
                WHERE demo_record_id = ?
            """, (demo_record_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("Expected exactly one deleted record.")
            result = _response(meta, data={"deleted_count": 1})
        else:
            existing = _read_demo_row(cursor, demo_record_id)
            if existing is None:
                raise RuntimeError("Locked demo record could not be read.")
            combined = {field: existing[field] for field in DEMO_BUSINESS_FIELDS}
            combined.update(changes)
            values = _validate_demo_business(combined)
            cursor.execute("""
                SELECT town_id FROM hdb_insights_demo.town WHERE town_name = ?
            """, (values["town_name"],))
            town = cursor.fetchone()
            if town is None:
                raise ValidationError("Unknown demo town_name.")
            cursor.execute("""
                SELECT flat_type_code FROM hdb_insights_demo.flat_type
                WHERE flat_type_code = ? AND flat_type_code <> 'ALL'
            """, (values["flat_type_code"],))
            if cursor.fetchone() is None:
                raise ValidationError("Unknown demo flat_type_code.")
            cursor.execute("""
                UPDATE hdb_insights_demo.demo_resale_transaction
                SET registration_month = ?, town_id = ?, flat_type_code = ?,
                    block = ?, street_name = ?, storey_lower = ?, storey_upper = ?,
                    floor_area_sqm = ?, flat_model = ?, lease_commence_year = ?,
                    remaining_lease_months = ?, resale_price = ?
                WHERE demo_record_id = ?
            """, (
                values["registration_month"], town["town_id"],
                values["flat_type_code"], values["block"], values["street_name"],
                values["storey_lower"], values["storey_upper"],
                values["floor_area_sqm"], values["flat_model"],
                values["lease_commence_year"], values["remaining_lease_months"],
                values["resale_price"], demo_record_id,
            ))
            updated = _read_demo_row(cursor, demo_record_id)
            if updated is None:
                raise RuntimeError("Updated record could not be read.")
            result = _response(meta, data=_serialise(updated))
        cursor.close()
        connection.commit()
        return result
    except ValidationError as error:
        return _response(meta, code="VALIDATION_ERROR", message=str(error))
    except DataNotReadyError:
        return _response(meta, code="DATA_NOT_READY",
                         message="A compatible analytical release has not been loaded.")
    except mariadb.Error as error:
        LOGGER.error("Demo modification failed; errno=%s", error.errno)
        if error.errno in {1062, 1205, 1213}:
            code = "CONFLICT"
        elif error.errno in {1040, 1042, 1045, 2002, 2003, 2006, 2013}:
            code = "DB_UNAVAILABLE"
        else:
            code = "INTERNAL_ERROR"
        return _response(meta, code=code,
                         message="The demo modification could not be confirmed.")
    except Exception as error:
        LOGGER.error("Demo modification failed: %s", type(error).__name__)
        return _response(meta, code="INTERNAL_ERROR",
                         message="The demo modification could not be completed.")
    finally:
        if connection is not None:
            connection.close()


def update_demo_resale(demo_record_id, changes):
    return _modify_demo_resale("update", demo_record_id, changes)


def delete_demo_resale(demo_record_id):
    return _modify_demo_resale("delete", demo_record_id)
