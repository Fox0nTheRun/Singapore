from getpass import getpass

import mariadb


def main():
    connection = mariadb.connect(
        host="127.0.0.1",
        port=3306,
        user="hdb_app",
        password=getpass("hdb_app password: "),
        database="hdb_insights",
        autocommit=False,
    )

    try:
        cursor = connection.cursor()

        cursor.execute("SELECT CURRENT_USER()")
        account = cursor.fetchone()[0]
        print(f"Connected as: {account}")

        if account != "hdb_app@localhost":
            raise RuntimeError("Unexpected database account.")

        cursor.execute("SELECT COUNT(*) FROM resale_transaction")
        count = cursor.fetchone()[0]

        if count != 240468:
            raise RuntimeError(f"Unexpected resale count: {count}")

        print(f"PASS: analytical SELECT allowed ({count:,} rows).")

        cursor.execute(
            "SELECT COUNT(*) FROM hdb_insights_demo.demo_seed"
        )
        print(
            "PASS: demo seed SELECT allowed "
            f"({cursor.fetchone()[0]} seeds)."
        )

        # WHERE 1=0 ensures these statements cannot change any rows,
        # even if the account accidentally has excessive permissions.
        forbidden_operations = [
            (
                "analytical UPDATE",
                """
                UPDATE hdb_insights.resale_transaction
                SET resale_price = resale_price
                WHERE 1 = 0
                """,
            ),
            (
                "demo identity UPDATE",
                """
                UPDATE hdb_insights_demo.demo_resale_transaction
                SET seed_record_id = seed_record_id
                WHERE 1 = 0
                """,
            ),
        ]

        for label, sql in forbidden_operations:
            try:
                cursor.execute(sql)
            except mariadb.Error as error:
                if error.errno not in (1142, 1143):
                    raise
                print(f"PASS: {label} denied (error {error.errno}).")
            else:
                raise RuntimeError(
                    f"FAIL: {label} was unexpectedly permitted."
                )
            finally:
                connection.rollback()

        print("All application permission checks passed.")

    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()