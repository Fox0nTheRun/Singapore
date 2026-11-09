"""Read-only, full-value reconciliation; safe to rerun on a loaded release."""
import getpass
import json
import os
import platform
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from load_mariadb import prepare, TABLES, FLATS, ETHNICITIES, AGES, CONTRACT, RELEASE
from src.hdb_insights.db.mariadb_connection import get_connection


def compare_rows(label, expected, actual):
    expected = Counter(expected)
    actual = Counter(actual)
    if expected != actual:
        missing = sum((expected - actual).values())
        unexpected = sum((actual - expected).values())
        raise ValueError(f'{label}: {missing} missing/different rows; '
                         f'{unexpected} unexpected/different rows')
    return {'component': label, 'rows': sum(actual.values()), 'result': 'PASS'}


def main():
    report = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'contract_version': CONTRACT, 'data_release_id': RELEASE,
        'python': platform.python_version(), 'checks': [], 'status': 'FAILED',
        'scope': 'All eight prepared datasets and analytical lookup values; read-only',
    }
    destination = Path(__file__).resolve().parent / 'docs/evidence/B/release_verification.json'
    connection = None
    original_password = os.environ.get('MARIADB_PASSWORD')
    try:
        report['mariadb_connector'] = version('mariadb')
        manifest, prepared = prepare()  # Validates raw and prepared hashes first.
        os.environ['MARIADB_PASSWORD'] = getpass.getpass('hdb_app password (Enter if blank): ')
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT DATABASE()')
        if cursor.fetchone()[0] != 'hdb_insights':
            raise ValueError('Verification must connect to hdb_insights.')
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
        cursor.execute('SELECT VERSION()')
        report['database_version'] = cursor.fetchone()[0]
        cursor.execute('SELECT metadata_id, contract_version, data_release_id FROM application_metadata')
        report['checks'].append(compare_rows('metadata', [(1, CONTRACT, RELEASE)], cursor.fetchall()))

        for filename, (headers, rows) in prepared.items():
            table = TABLES[filename]
            cursor.execute(f'SHOW COLUMNS FROM `{table}`')
            db_columns = {row[0] for row in cursor.fetchall()}
            expected_columns = set(headers)
            if filename == 'resale.csv':
                expected_columns.remove('town_name')
                expected_columns.add('town_id')
            if expected_columns != db_columns:
                raise ValueError(f'{table}: column contract mismatch')
            # Identifiers validated against actual columns above.
            if filename == 'resale.csv':
                columns = ', '.join('t.town_name' if h == 'town_name' else f'r.`{h}`' for h in headers)
                query = f'SELECT {columns} FROM resale_transaction r LEFT JOIN town t ON t.town_id = r.town_id'
            else:
                columns = ', '.join(f'`{h}`' for h in headers)
                query = f'SELECT {columns} FROM `{table}`'
            cursor.execute(query)
            result = compare_rows(table, (tuple(r[h] for h in headers) for r in rows), cursor.fetchall())
            report['checks'].append(result)
            print(f"PASS: {table}: {result['rows']:,} rows, all fields match")

        references = [
            ('source_dataset', 'dataset_id, source_filename, source_file_sha256, source_row_count',
             [(s['dataset_id'], s['source_filename'], s['source_sha256'], s['row_count']) for s in manifest['sources']]),
            ('flat_type', 'flat_type_code, display_label, is_total',
             [(c, label, int(c == 'ALL')) for c, label in FLATS.items()]),
            ('ethnic_group', 'ethnic_group_code, display_label, is_total',
             [(c, label, int(c == 'ALL')) for c, label in ETHNICITIES.items()]),
            ('age_group', 'age_group_code, display_label, sort_order', AGES),
            ('town', 'town_name', [(n,) for n in sorted({r['town_name'] for r in prepared['resale.csv'][1]})]),
        ]
        for table, columns, expected in references:
            cursor.execute(f'SELECT {columns} FROM `{table}`')
            report['checks'].append(compare_rows(table, expected, cursor.fetchall()))
        # Inventory only: never delete unidentified records automatically.
        cursor.execute('SELECT demo_record_id, seed_record_id, base_data_release_id, resale_price FROM hdb_insights_demo.demo_resale_transaction ORDER BY demo_record_id')
        report['remaining_demo_records'] = [dict(zip(
            ['demo_record_id', 'seed_record_id', 'base_data_release_id', 'resale_price'], row
        )) for row in cursor.fetchall()]
        cursor.close()
        report['status'] = 'PASS'
        print('PASS: Analytical metadata and reference values match.')
        print('Remaining demo records:', len(report['remaining_demo_records']))
        for row in report['remaining_demo_records']:
            print(row['demo_record_id'], row['resale_price'])
    except Exception as error:
        report['error_type'] = type(error).__name__
        print('Verification failed:', type(error).__name__)
        raise
    finally:
        if connection is not None:
            connection.close()
        if original_password is None:
            os.environ.pop('MARIADB_PASSWORD', None)
        else:
            os.environ['MARIADB_PASSWORD'] = original_password
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
        print('Evidence:', destination)


if __name__ == '__main__':
    main()
