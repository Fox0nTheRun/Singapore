import os

import mariadb


def get_connection():
    """Open an application connection using environment configuration."""
    password = os.environ.get("MARIADB_PASSWORD")

    if password is None:
    	raise ValueError("MARIADB_PASSWORD is not configured.")

    connection = mariadb.connect(
        host=os.environ.get("MARIADB_HOST", "127.0.0.1"),
        port=int(os.environ.get("MARIADB_PORT", "3306")),
        user=os.environ.get("MARIADB_USER", "hdb_app"),
        password=password,
        database=os.environ.get("MARIADB_DATABASE", "hdb_insights"),
        autocommit=False,
    )

    try:
        cursor = connection.cursor()

        # Consistent decimal division for analytical calculations.
        cursor.execute("SET SESSION div_precision_increment = 12")

        # Reject invalid values rather than silently coercing them.
        cursor.execute(
            """
            SET SESSION sql_mode =
            'STRICT_ALL_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'
            """
        )

        cursor.execute("SET SESSION time_zone = '+00:00'")
        cursor.close()

        return connection

    except Exception:
        connection.close()
        raise