"""
tests/load_test_data.py
Loads all test data from tests/data/cst_test_data.db into TM1.
Safe to re-run — clears target cubes before loading.

Load sequence:
  1.  CST Account Config           (gl_input, gl_accounts, account_driver, apportionment_config)
  2.  CST Pool to Pool Config      (pool_to_pool_driver_input, pool_to_pool_drivers)
  3.  CST Pool Config              (driver_assumptions, driver_values, pool_drivers)
  4.  CST Activity to Activity Config (activity_to_activity_driver_input, activity_to_activity_drivers)
  5.  CST Activity Config          (activity_driver_assumptions, activity_driver_values, activity_driver_input)

Sentinel rules (Config cube pattern):
  - Cost Pool  = 'Input'  when row is not a pct-split (gl amount, flag, driver code)
  - Cost Centre = 'Input' when row is not CC-specific (pool-to-pool, activity-to-activity)
  - Driver = 'Input'      when row is not driver-specific (basis strings, activity pct)
  - Activity = 'Input'    when row is not activity-specific (basis strings, driver values)
  - Service Line = 'Input' when row is not SL-specific (basis strings, driver values)
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

DB = Path(__file__).resolve().parent / 'data' / 'cst_test_data.db'

# Cube names
ACCOUNT_CONFIG_CUBE  = 'CST Account Config'
P2P_CONFIG_CUBE      = 'CST Pool to Pool Config'
POOL_CONFIG_CUBE     = 'CST Pool Config'
A2A_CONFIG_CUBE      = 'CST Activity to Activity Config'
ACTIVITY_CONFIG_CUBE = 'CST Activity Config'

# Dimension lists
ACCOUNT_CONFIG_DIMS  = ['GBL Period', 'GBL Version', 'GBL Account', 'GBL Cost Centre',
                        'CST Cost Pool', 'CST Account Config Measure']
P2P_CONFIG_DIMS      = ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Cost Pool Dest',
                        'GBL Cost Centre', 'CST Pool to Pool Config Measure']
POOL_CONFIG_DIMS     = ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Driver',
                        'CST Activity', 'CST Pool Config Measure']
A2A_CONFIG_DIMS      = ['GBL Period', 'GBL Version', 'CST Activity', 'CST Activity Dest',
                        'GBL Cost Centre', 'CST Activity to Activity Config Measure']
ACTIVITY_CONFIG_DIMS = ['GBL Period', 'GBL Version', 'CST Activity', 'CST Driver',
                        'CST Service Line', 'CST Activity Config Measure']


def _load_account_config(tm1, conn):
    total = 0

    # GL Amount — Cost Pool='Input' (not a pct-split row)
    rows = conn.execute(
        'SELECT period, version, account_code, department_code, amount FROM gl_input'
    ).fetchall()
    cells = {(p, v, acct, dept, 'Input', 'Amount'): amt for p, v, acct, dept, amt in rows}
    tm1.cells.write_values(ACCOUNT_CONFIG_CUBE, cells, dimensions=ACCOUNT_CONFIG_DIMS)
    total += len(cells)

    # Is Apportioned flag — CC='Input', Cost Pool='Input' (account-level flag)
    pvs      = conn.execute('SELECT DISTINCT period, version FROM gl_input').fetchall()
    accounts = conn.execute('SELECT account_code, account_type FROM gl_accounts').fetchall()
    cells = {}
    for period, version in pvs:
        for acct, atype in accounts:
            cells[(period, version, acct, 'Input', 'Input', 'Is Apportioned')] = (
                1 if atype == 'Overhead' else 0
            )
    tm1.cells.write_values(ACCOUNT_CONFIG_CUBE, cells, dimensions=ACCOUNT_CONFIG_DIMS)
    total += len(cells)

    # Driver Percentage Share — actual Cost Pool used as key
    rows = conn.execute(
        'SELECT period, version, cost_centre_code, account_code, cost_pool_code, apportionment_pct '
        'FROM apportionment_config'
    ).fetchall()
    cells = {(p, v, acct, cc, pool, 'Driver Percentage Share'): pct
             for p, v, cc, acct, pool, pct in rows}
    tm1.cells.write_values(ACCOUNT_CONFIG_CUBE, cells, dimensions=ACCOUNT_CONFIG_DIMS)
    total += len(cells)

    return total


def _load_p2p_config(tm1, conn):
    total = 0

    # Driver Value + Description — CC='Input'
    rows = conn.execute(
        'SELECT period, version, cost_pool_code, cost_pool_dest_code, driver_value, driver_description '
        'FROM pool_to_pool_driver_input'
    ).fetchall()
    num_cells = {(p, v, pool, dest, 'Input', 'Driver Value'): val
                 for p, v, pool, dest, val, _ in rows}
    str_cells = {(p, v, pool, dest, 'Input', 'Driver Description'): desc
                 for p, v, pool, dest, _, desc in rows}
    tm1.cells.write_values(P2P_CONFIG_CUBE, num_cells, dimensions=P2P_CONFIG_DIMS)
    tm1.cells.write_values(P2P_CONFIG_CUBE, str_cells, dimensions=P2P_CONFIG_DIMS)
    total += len(rows) * 2

    # Driver Percentage Share — CC='Input'
    rows = conn.execute(
        'SELECT period, version, cost_pool_code, cost_pool_dest_code, driver_percentage_share '
        'FROM pool_to_pool_drivers'
    ).fetchall()
    cells = {(p, v, pool, dest, 'Input', 'Driver Percentage Share'): pct
             for p, v, pool, dest, pct in rows}
    tm1.cells.write_values(P2P_CONFIG_CUBE, cells, dimensions=P2P_CONFIG_DIMS)
    total += len(cells)

    return total


def _load_pool_config(tm1, conn):
    total = 0

    # Pool to Activity Basis — Driver='Input', Activity='Input' (one code per pool)
    rows = conn.execute(
        'SELECT period, version, cost_pool_code, pool_to_activity_basis FROM driver_assumptions'
    ).fetchall()
    str_cells = {(p, v, pool, 'Input', 'Input', 'Pool to Activity Basis'): basis
                 for p, v, pool, basis in rows}
    tm1.cells.write_values(POOL_CONFIG_CUBE, str_cells, dimensions=POOL_CONFIG_DIMS)
    total += len(str_cells)

    # Driver Value per pool × driver — Activity='Input'
    rows = conn.execute(
        'SELECT period, version, cost_pool_code, driver_code, driver_value FROM driver_values'
    ).fetchall()
    cells = {(p, v, pool, drv, 'Input', 'Driver Value'): val for p, v, pool, drv, val in rows}
    tm1.cells.write_values(POOL_CONFIG_CUBE, cells, dimensions=POOL_CONFIG_DIMS)
    total += len(cells)

    # Driver Percentage Share is rule-computed from Driver Value via Pool to Activity Basis.
    # Not loaded here — TM1 rule handles it.

    return total


def _load_a2a_config(tm1, conn):
    total = 0

    # Driver Value + Description — CC='Input'
    rows = conn.execute(
        'SELECT period, version, activity_code, activity_dest_code, driver_value, driver_description '
        'FROM activity_to_activity_driver_input'
    ).fetchall()
    num_cells = {(p, v, act, dest, 'Input', 'Driver Value'): val
                 for p, v, act, dest, val, _ in rows}
    str_cells = {(p, v, act, dest, 'Input', 'Driver Description'): desc
                 for p, v, act, dest, _, desc in rows}
    tm1.cells.write_values(A2A_CONFIG_CUBE, num_cells, dimensions=A2A_CONFIG_DIMS)
    tm1.cells.write_values(A2A_CONFIG_CUBE, str_cells, dimensions=A2A_CONFIG_DIMS)
    total += len(rows) * 2

    # Driver Percentage Share — CC='Input'
    rows = conn.execute(
        'SELECT period, version, activity_code, activity_dest_code, driver_percentage_share '
        'FROM activity_to_activity_drivers'
    ).fetchall()
    cells = {(p, v, act, dest, 'Input', 'Driver Percentage Share'): pct
             for p, v, act, dest, pct in rows}
    tm1.cells.write_values(A2A_CONFIG_CUBE, cells, dimensions=A2A_CONFIG_DIMS)
    total += len(cells)

    return total


def _load_activity_config(tm1, conn):
    total = 0

    # Activity to SL Basis (String) — Driver='Input', SL='Input'
    rows = conn.execute(
        'SELECT period, version, activity_code, activity_to_sl_basis '
        'FROM activity_driver_assumptions'
    ).fetchall()
    cells = {(p, v, act, 'Input', 'Input', 'Activity to Service Line Basis'): basis
             for p, v, act, basis in rows}
    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, cells, dimensions=ACTIVITY_CONFIG_DIMS)
    total += len(cells)

    # Driver Value per activity × driver — SL='Input'
    rows = conn.execute(
        'SELECT period, version, activity_code, driver_code, driver_value '
        'FROM activity_driver_values'
    ).fetchall()
    cells = {(p, v, act, drv, 'Input', 'Driver Value'): val for p, v, act, drv, val in rows}
    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, cells, dimensions=ACTIVITY_CONFIG_DIMS)
    total += len(cells)

    # Input Volume + Description per activity × service line — Driver='Input'
    rows = conn.execute(
        'SELECT period, version, activity_code, service_line_code, driver_value, driver_description '
        'FROM activity_driver_input'
    ).fetchall()
    num_cells = {(p, v, act, 'Input', sl, 'Input Volume'): val
                 for p, v, act, sl, val, _ in rows}
    str_cells = {(p, v, act, 'Input', sl, 'Input Description'): desc
                 for p, v, act, sl, _, desc in rows}
    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, num_cells, dimensions=ACTIVITY_CONFIG_DIMS)
    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, str_cells, dimensions=ACTIVITY_CONFIG_DIMS)
    total += len(rows) * 2

    return total


def main():
    conn = sqlite3.connect(DB)

    print(f"\n{'─'*60}")
    print("  Load test data → TM1")
    print(f"  Source: {DB.name}")
    print(f"{'─'*60}")

    with get_tm1_service() as tm1:

        print("\n  1. CST Account Config")
        tm1.cells.clear(ACCOUNT_CONFIG_CUBE)
        n = _load_account_config(tm1, conn)
        print(f"     ✓ {n} cells written")

        print("\n  2. CST Pool to Pool Config")
        tm1.cells.clear(P2P_CONFIG_CUBE)
        n = _load_p2p_config(tm1, conn)
        print(f"     ✓ {n} cells written")

        print("\n  3. CST Pool Config")
        tm1.cells.clear(POOL_CONFIG_CUBE)
        n = _load_pool_config(tm1, conn)
        print(f"     ✓ {n} cells written")

        print("\n  4. CST Activity to Activity Config")
        tm1.cells.clear(A2A_CONFIG_CUBE)
        n = _load_a2a_config(tm1, conn)
        print(f"     ✓ {n} cells written")

        print("\n  5. CST Activity Config")
        tm1.cells.clear(ACTIVITY_CONFIG_CUBE)
        n = _load_activity_config(tm1, conn)
        print(f"     ✓ {n} cells written")

    conn.close()
    print(f"\n{'─'*60}")
    print("  Done.")
    print(f"{'─'*60}\n")


if __name__ == '__main__':
    main()
