import os
from getpass import getpass

from src.hdb_insights.db.mariadb_connection import get_connection


def main():
    # Prompt only in this standalone check, not in the reusable module.
    os.environ["MARIADB_PASSWORD"] = getpass("hdb_app password: ")

    connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT contract_version, data_release_id
            FROM application_metadata
            WHERE metadata_id = 1
            """
        )
        row = cursor.fetchone()

        expected = (
            "HDBI-1.0.0",
            "150921447b27_c1.0.0_t0.1.2",
        )

        if row != expected:
            raise RuntimeError(f"Unexpected database metadata: {row!r}")

        print(f"Contract: {row[0]}")
        print(f"Data release: {row[1]}")
        print("PASS: reusable connection module works.")

        cursor.close()

    finally:
        connection.rollback()
        connection.close()
        os.environ.pop("MARIADB_PASSWORD", None)


if __name__ == "__main__":
    main()