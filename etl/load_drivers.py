"""
etl/load_drivers.py
Loads driver configuration from SQL into TM1 Config cubes.
Writes VAL01-VAL04 validation results to CST Apportionment Reconciliation.

Loads:
  - CST Pool Config           (basis strings, driver values)
  - CST Activity Config       (basis strings, driver values, input volumes)
  - CST Pool to Pool Config   (driver values, descriptions)
  - CST Activity to Activity Config (driver values, descriptions)

Validation checks written to TM1:
  VAL01 — Driver value completeness: all pools have values loaded for their basis
  VAL02 — Driver coverage: all activities have values for their basis
  VAL03 — Driver SQL vs TM1: loaded values match SQL source
  VAL04 — Account config coverage: all overhead accounts have pool assignments

Usage:
    python3 etl/load_drivers.py                          # all periods/versions in DB
    python3 etl/load_drivers.py --period 2025-04         # specific period
    python3 etl/load_drivers.py --period 2025-04 --version Budget
"""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service
from etl.utils import get_version_periods

DB = Path(__file__).resolve().parent.parent / 'tests' / 'data' / 'cst_test_data.db'

RECON_CUBE = 'CST Apportionment Reconciliation'
RECON_DIMS = ['GBL Period', 'GBL Version', 'CST Reconciliation Check',
              'CST Apportionment Reconciliation Measure']

POOL_CONFIG_CUBE  = 'CST Pool Config'
POOL_CONFIG_DIMS  = ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Driver',
                     'CST Activity', 'CST Pool Config Measure']

P2P_CONFIG_CUBE   = 'CST Pool to Pool Config'
P2P_CONFIG_DIMS   = ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Cost Pool Dest',
                     'GBL Cost Centre', 'CST Pool to Pool Config Measure']

ACTIVITY_CONFIG_CUBE = 'CST Activity Config'
ACTIVITY_CONFIG_DIMS = ['GBL Period', 'GBL Version', 'CST Activity', 'CST Driver',
                        'CST Service Line', 'CST Activity Config Measure']

A2A_CONFIG_CUBE   = 'CST Activity to Activity Config'
A2A_CONFIG_DIMS   = ['GBL Period', 'GBL Version', 'CST Activity', 'CST Activity Dest',
                     'GBL Cost Centre', 'CST Activity to Activity Config Measure']


def _write_val(tm1, period, version, check, status, message):
    tm1.cells.write_value(status,  RECON_CUBE, (period, version, check, 'Status'),  dimensions=RECON_DIMS)
    tm1.cells.write_value(message, RECON_CUBE, (period, version, check, 'Message'), dimensions=RECON_DIMS)


def _load_pool_config(tm1, conn, period_filter, version_filter):
    where, params = _build_filter(period_filter, version_filter)

    # Basis strings — Driver='Input', Activity='Input'
    rows = conn.execute(
        f'SELECT period, version, cost_pool_code, pool_to_activity_basis '
        f'FROM driver_assumptions {where}', params
    ).fetchall()
    str_cells = {(p, v, pool, 'Input', 'Input', 'Pool to Activity Basis'): basis
                 for p, v, pool, basis in rows}

    # Driver values per pool × driver — Activity='Input'
    rows = conn.execute(
        f'SELECT period, version, cost_pool_code, driver_code, driver_value '
        f'FROM driver_values {where}', params
    ).fetchall()
    num_cells = {(p, v, pool, drv, 'Input', 'Driver Value'): val
                 for p, v, pool, drv, val in rows}

    tm1.cells.write_values(POOL_CONFIG_CUBE, str_cells, dimensions=POOL_CONFIG_DIMS)
    tm1.cells.write_values(POOL_CONFIG_CUBE, num_cells, dimensions=POOL_CONFIG_DIMS)
    return len(str_cells) + len(num_cells)


def _load_p2p_config(tm1, conn, period_filter, version_filter):
    where, params = _build_filter(period_filter, version_filter)

    rows = conn.execute(
        f'SELECT period, version, cost_pool_code, cost_pool_dest_code, driver_value, driver_description, active '
        f'FROM pool_to_pool_driver_input {where}', params
    ).fetchall()
    num_cells    = {(p, v, pool, dest, 'Input', 'Driver Value'): val
                    for p, v, pool, dest, val, _, _a in rows}
    str_cells    = {(p, v, pool, dest, 'Input', 'Driver Description'): desc
                    for p, v, pool, dest, _, desc, _a in rows}
    active_cells = {(p, v, pool, dest, 'Input', 'Active'): active
                    for p, v, pool, dest, _v, _d, active in rows}

    tm1.cells.write_values(P2P_CONFIG_CUBE, num_cells,    dimensions=P2P_CONFIG_DIMS)
    tm1.cells.write_values(P2P_CONFIG_CUBE, str_cells,    dimensions=P2P_CONFIG_DIMS)
    tm1.cells.write_values(P2P_CONFIG_CUBE, active_cells, dimensions=P2P_CONFIG_DIMS)
    return len(rows) * 3


def _load_activity_config(tm1, conn, period_filter, version_filter):
    where, params = _build_filter(period_filter, version_filter)

    # Basis strings — Driver='Input', SL='Input'
    rows = conn.execute(
        f'SELECT period, version, activity_code, activity_to_sl_basis '
        f'FROM activity_driver_assumptions {where}', params
    ).fetchall()
    str_cells = {(p, v, act, 'Input', 'Input', 'Activity to Service Line Basis'): basis
                 for p, v, act, basis in rows}

    # Driver values per activity × driver — SL='Input'
    rows = conn.execute(
        f'SELECT period, version, activity_code, driver_code, driver_value '
        f'FROM activity_driver_values {where}', params
    ).fetchall()
    num_cells = {(p, v, act, drv, 'Input', 'Driver Value'): val
                 for p, v, act, drv, val in rows}

    # Input volumes per activity × service line — Driver='Input'
    rows = conn.execute(
        f'SELECT period, version, activity_code, service_line_code, driver_value, driver_description '
        f'FROM activity_driver_input {where}', params
    ).fetchall()
    vol_cells  = {(p, v, act, 'Input', sl, 'Input Volume'):      val
                  for p, v, act, sl, val, _ in rows}
    desc_cells = {(p, v, act, 'Input', sl, 'Input Description'): desc
                  for p, v, act, sl, _, desc in rows}

    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, str_cells,  dimensions=ACTIVITY_CONFIG_DIMS)
    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, num_cells,  dimensions=ACTIVITY_CONFIG_DIMS)
    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, vol_cells,  dimensions=ACTIVITY_CONFIG_DIMS)
    tm1.cells.write_values(ACTIVITY_CONFIG_CUBE, desc_cells, dimensions=ACTIVITY_CONFIG_DIMS)
    return len(str_cells) + len(num_cells) + len(rows) * 2


def _load_a2a_config(tm1, conn, period_filter, version_filter):
    where, params = _build_filter(period_filter, version_filter)

    rows = conn.execute(
        f'SELECT period, version, activity_code, activity_dest_code, driver_value, driver_description '
        f'FROM activity_to_activity_driver_input {where}', params
    ).fetchall()
    num_cells = {(p, v, act, dest, 'Input', 'Driver Value'): val
                 for p, v, act, dest, val, _ in rows}
    str_cells = {(p, v, act, dest, 'Input', 'Driver Description'): desc
                 for p, v, act, dest, _, desc in rows}

    tm1.cells.write_values(A2A_CONFIG_CUBE, num_cells, dimensions=A2A_CONFIG_DIMS)
    tm1.cells.write_values(A2A_CONFIG_CUBE, str_cells, dimensions=A2A_CONFIG_DIMS)
    return len(rows) * 2


def _validate(tm1, conn, period_filter, version_filter):
    """Run VAL01-VAL04 checks and write results to Reconciliation cube."""
    where, params = _build_filter(period_filter, version_filter)
    pvs = conn.execute(
        f'SELECT DISTINCT period, version FROM driver_assumptions {where}', params
    ).fetchall()

    for period, version in pvs:

        # VAL01 — Driver value completeness: every pool has driver values loaded for its basis
        basis_rows = conn.execute(
            'SELECT cost_pool_code, pool_to_activity_basis FROM driver_assumptions '
            'WHERE period=? AND version=?', (period, version)
        ).fetchall()
        missing = []
        for pool, basis in basis_rows:
            count = conn.execute(
                'SELECT COUNT(*) FROM driver_values WHERE period=? AND version=? '
                'AND cost_pool_code=? AND driver_code=?', (period, version, pool, basis)
            ).fetchone()[0]
            if count == 0:
                missing.append(f"{pool}:{basis}")
        if missing:
            _write_val(tm1, period, version, 'VAL01', 'WARNING',
                       f"Pools with no driver values (will apportion zero): {', '.join(missing)}")
        else:
            _write_val(tm1, period, version, 'VAL01', 'PASS',
                       'All pools have driver values for their basis')

        # VAL02 — Driver coverage: every activity has input volumes loaded
        act_rows = conn.execute(
            'SELECT DISTINCT activity_code FROM activity_driver_assumptions '
            'WHERE period=? AND version=?', (period, version)
        ).fetchall()
        missing = []
        for (act,) in act_rows:
            count = conn.execute(
                'SELECT COUNT(*) FROM activity_driver_input WHERE period=? AND version=? '
                'AND activity_code=?', (period, version, act)
            ).fetchone()[0]
            if count == 0:
                missing.append(act)
        if missing:
            _write_val(tm1, period, version, 'VAL02', 'FAIL',
                       f"Missing input volumes: {', '.join(missing)}")
        else:
            _write_val(tm1, period, version, 'VAL02', 'PASS',
                       'All activities have input volumes loaded')

        # VAL03 — Driver SQL vs TM1: spot-check total driver values match
        sql_total = conn.execute(
            'SELECT COALESCE(SUM(driver_value),0) FROM driver_values '
            'WHERE period=? AND version=?', (period, version)
        ).fetchone()[0]
        mdx = (
            f"SELECT {{[GBL Period].[{period}]}} ON 0, "
            f"{{[CST Cost Pool].[Total Cost Pools]}} ON 1 "
            f"FROM [CST Pool Config] "
            f"WHERE ([GBL Version].[{version}], [CST Driver].[Total Drivers], "
            f"[CST Activity].[Input], [CST Pool Config Measure].[Driver Value])"
        )
        try:
            result   = tm1.cells.execute_mdx(mdx)
            tm1_total = list(result.values())[0].get('Value', 0) or 0
            variance  = abs(sql_total - tm1_total)
            if variance > 0.01:
                _write_val(tm1, period, version, 'VAL03', 'FAIL',
                           f"SQL total {sql_total:.2f} vs TM1 total {tm1_total:.2f} — variance {variance:.2f}")
            else:
                _write_val(tm1, period, version, 'VAL03', 'PASS',
                           f"Driver totals match: {tm1_total:.2f}")
        except Exception as e:
            _write_val(tm1, period, version, 'VAL03', 'WARNING', f"Could not verify: {e}")

        # VAL04 — Account config coverage: all overhead accounts have pool assignments
        overhead = conn.execute(
            "SELECT account_code FROM gl_accounts WHERE account_type='Overhead'"
        ).fetchall()
        assigned = conn.execute(
            'SELECT DISTINCT account_code FROM apportionment_config '
            'WHERE period=? AND version=?', (period, version)
        ).fetchall()
        assigned_set = {r[0] for r in assigned}
        missing = [r[0] for r in overhead if r[0] not in assigned_set]
        if missing:
            _write_val(tm1, period, version, 'VAL04', 'FAIL',
                       f"Overhead accounts without pool assignment: {', '.join(missing)}")
        else:
            _write_val(tm1, period, version, 'VAL04', 'PASS',
                       'All overhead accounts have pool assignments')


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


def main(period=None, version=None):
    conn = sqlite3.connect(DB)

    print(f"\n{'─'*60}")
    print("  ETL — Load Drivers → TM1")
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

        def _load(p, v):
            print(f"\n  Period {p} / {v}")
            print("    1. CST Pool Config")
            n = _load_pool_config(tm1, conn, p, v)
            print(f"       ✓ {n} cells written")
            print("    2. CST Pool to Pool Config")
            n = _load_p2p_config(tm1, conn, p, v)
            print(f"       ✓ {n} cells written")
            print("    3. CST Activity Config")
            n = _load_activity_config(tm1, conn, p, v)
            print(f"       ✓ {n} cells written")
            print("    4. CST Activity to Activity Config")
            n = _load_a2a_config(tm1, conn, p, v)
            print(f"       ✓ {n} cells written")
            print("    5. Validation checks")
            _validate(tm1, conn, p, v)
            print(f"       ✓ VAL01-VAL04 written")

        if periods:
            for p in periods:
                _load(p, version)
        else:
            # single period/version or all in DB
            print("\n  1. CST Pool Config")
            n = _load_pool_config(tm1, conn, period, version)
            print(f"     ✓ {n} cells written")
            print("\n  2. CST Pool to Pool Config")
            n = _load_p2p_config(tm1, conn, period, version)
            print(f"     ✓ {n} cells written")
            print("\n  3. CST Activity Config")
            n = _load_activity_config(tm1, conn, period, version)
            print(f"     ✓ {n} cells written")
            print("\n  4. CST Activity to Activity Config")
            n = _load_a2a_config(tm1, conn, period, version)
            print(f"     ✓ {n} cells written")
            print("\n  5. Validation checks")
            _validate(tm1, conn, period, version)
            print(f"     ✓ VAL01-VAL04 written to Reconciliation cube")

    conn.close()
    print(f"\n{'─'*60}")
    print("  Done. Review VAL checks in PAW before running apportionment.")
    print(f"{'─'*60}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--period',  default=None)
    parser.add_argument('--version', default=None)
    args = parser.parse_args()
    main(args.period, args.version)
