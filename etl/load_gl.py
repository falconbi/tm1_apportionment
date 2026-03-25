"""
etl/load_gl.py
Loads GL amounts and account configuration from SQL into CST Account Config.
Writes a VAL check for GL load completeness to CST Apportionment Reconciliation.

Loads:
  - GL Amount per account / cost centre / period / version
  - Is Apportioned flag per account
  - Driver Percentage Share per account / cost centre / cost pool

Usage:
    python3 etl/load_gl.py                          # all periods/versions in DB
    python3 etl/load_gl.py --period 2025-04         # specific period
    python3 etl/load_gl.py --period 2025-04 --version Budget
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service
from etl.utils import get_version_periods

DB = Path(__file__).resolve().parent.parent / 'tests' / 'data' / 'cst_test_data.db'

ACCOUNT_CONFIG_CUBE = 'CST Account Config'
ACCOUNT_CONFIG_DIMS = ['GBL Period', 'GBL Version', 'GBL Account', 'GBL Cost Centre',
                       'CST Cost Pool', 'CST Account Config Measure']

RECON_CUBE = 'CST Apportionment Reconciliation'
RECON_DIMS = ['GBL Period', 'GBL Version', 'CST Reconciliation Check',
              'CST Apportionment Reconciliation Measure']


def _write_val(tm1, period, version, check, status, message):
    tm1.cells.write_value(status,  RECON_CUBE, (period, version, check, 'Status'),  dimensions=RECON_DIMS)
    tm1.cells.write_value(message, RECON_CUBE, (period, version, check, 'Message'), dimensions=RECON_DIMS)


def _build_filter(period, version):
    clauses, params = [], []
    if period:
        clauses.append('period=?')
        params.append(period)
    if version:
        clauses.append('version=?')
        params.append(version)
    where = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    return where, params


def _load_account_config(tm1, conn, period_filter, version_filter):
    where, params = _build_filter(period_filter, version_filter)
    total = 0

    # GL Amount — Cost Pool='Input' (not a pct-split row)
    rows = conn.execute(
        f'SELECT period, version, account_code, department_code, amount FROM gl_input {where}',
        params
    ).fetchall()
    cells = {(p, v, acct, dept, 'Input', 'Amount'): amt for p, v, acct, dept, amt in rows}
    tm1.cells.write_values(ACCOUNT_CONFIG_CUBE, cells, dimensions=ACCOUNT_CONFIG_DIMS)
    total += len(cells)

    # Is Apportioned flag — CC='Input', Cost Pool='Input' (account-level flag)
    pvs      = conn.execute(
        f'SELECT DISTINCT period, version FROM gl_input {where}', params
    ).fetchall()
    accounts = conn.execute('SELECT account_code, account_type FROM gl_accounts').fetchall()
    cells = {}
    for period, version in pvs:
        for acct, atype in accounts:
            cells[(period, version, acct, 'Input', 'Input', 'Is Apportioned')] = (
                1 if atype == 'Overhead' else 0
            )
    tm1.cells.write_values(ACCOUNT_CONFIG_CUBE, cells, dimensions=ACCOUNT_CONFIG_DIMS)
    total += len(cells)

    # Driver Percentage Share — exact Cost Pool used as key
    rows = conn.execute(
        f'SELECT period, version, cost_centre_code, account_code, cost_pool_code, apportionment_pct '
        f'FROM apportionment_config {where}',
        params
    ).fetchall()
    cells = {(p, v, acct, cc, pool, 'Driver Percentage Share'): pct
             for p, v, cc, acct, pool, pct in rows}
    tm1.cells.write_values(ACCOUNT_CONFIG_CUBE, cells, dimensions=ACCOUNT_CONFIG_DIMS)
    total += len(cells)

    return total


def _validate(tm1, conn, period_filter, version_filter):
    """Check all overhead accounts have GL amounts loaded and write VAL check."""
    where, params = _build_filter(period_filter, version_filter)
    pvs = conn.execute(
        f'SELECT DISTINCT period, version FROM gl_input {where}', params
    ).fetchall()

    overhead_accounts = [r[0] for r in conn.execute(
        "SELECT account_code FROM gl_accounts WHERE account_type='Overhead'"
    ).fetchall()]

    for period, version in pvs:
        loaded = {r[0] for r in conn.execute(
            'SELECT DISTINCT account_code FROM gl_input WHERE period=? AND version=?',
            (period, version)
        ).fetchall()}
        missing = [a for a in overhead_accounts if a not in loaded]
        sql_total = conn.execute(
            "SELECT COALESCE(SUM(ABS(amount)),0) FROM gl_input "
            "WHERE period=? AND version=?", (period, version)
        ).fetchone()[0]

        if missing:
            _write_val(tm1, period, version, 'VAL04',
                       'WARNING',
                       f"Overhead accounts with no GL data: {', '.join(missing)}")
        else:
            _write_val(tm1, period, version, 'VAL04',
                       'PASS',
                       f"All overhead accounts loaded — total {sql_total:,.2f}")


def main(period=None, version=None):
    conn = sqlite3.connect(DB)

    print(f"\n{'─'*60}")
    print("  ETL — Load GL Data → TM1")
    print(f"  Source: {DB.name}")

    with get_tm1_service() as tm1:

        # If version given but no period — use TM1 version period range
        periods = None
        if version and not period:
            periods = get_version_periods(tm1, version)
            print(f"  Version: {version}  ({periods[0]} → {periods[-1]}, {len(periods)} periods)")
        elif period:
            print(f"  Period:  {period}")
            if version:
                print(f"  Version: {version}")
        print(f"{'─'*60}")

        if periods:
            for p in periods:
                print(f"\n  Period {p} / {version}")
                n = _load_account_config(tm1, conn, p, version)
                print(f"    ✓ {n} cells written")
                _validate(tm1, conn, p, version)
                print(f"    ✓ VAL04 written")
        else:
            print("\n  1. CST Account Config")
            n = _load_account_config(tm1, conn, period, version)
            print(f"     ✓ {n} cells written")
            print("\n  2. Validation checks")
            _validate(tm1, conn, period, version)
            print(f"     ✓ VAL04 written to Reconciliation cube")

    conn.close()
    print(f"\n{'─'*60}")
    print("  Done. Review VAL04 in PAW before running apportionment.")
    print(f"{'─'*60}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--period',  default=None)
    parser.add_argument('--version', default=None)
    args = parser.parse_args()
    main(args.period, args.version)
