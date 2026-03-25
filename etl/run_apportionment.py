"""
etl/run_apportionment.py
Runs the full CST apportionment chain for a given period and version.

Stages:
  1  — Account → Pool         (TM1 rules, always live)
  1b — Pool → Pool            (Python iteration — reciprocal)
  2  — Pool → Activity        (TM1 rules, always live)
  2b — Activity → Activity    (Python iteration — reciprocal)
  3  — Activity → Service Line (TM1 rules, always live)

Gate control:
  Reads VAL01-VAL04 from Reconciliation cube before running.
  Aborts if any check is FAIL — ensures clean data before apportionment.

Usage:
    python3 etl/run_apportionment.py --period 2025-04 --version Budget
    python3 etl/run_apportionment.py --period 2025-04 --version Budget --max-iter 50
    python3 etl/run_apportionment.py --period 2025-04 --version Budget --force   # skip VAL gate
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service
from etl.utils import get_version_periods
from config import CST_CONFIG

OVERHEAD_CONSOLIDATION = CST_CONFIG['overhead_consolidation']

RECON_CUBE = 'CST Apportionment Reconciliation'
RECON_DIMS = ['GBL Period', 'GBL Version', 'CST Reconciliation Check',
              'CST Apportionment Reconciliation Measure']

VAL_CHECKS = ['VAL01', 'VAL02', 'VAL03', 'VAL04']
RC_CHECKS  = ['RC01', 'RC03', 'RC05']


def _read_val_status(tm1, period, version):
    """Read all VAL check statuses from Reconciliation cube."""
    results = {}
    for check in VAL_CHECKS:
        status = tm1.cells.get_value(
            RECON_CUBE, f'{period},{version},{check},Status',
            dimensions=RECON_DIMS
        ) or 'NO DATA'
        message = tm1.cells.get_value(
            RECON_CUBE, f'{period},{version},{check},Message',
            dimensions=RECON_DIMS
        ) or ''
        results[check] = {'status': status, 'message': message}
    return results


def _read_rc_results(tm1, period, version):
    """Read RC check results from Reconciliation cube."""
    results = {}
    for check in RC_CHECKS:
        input_total  = tm1.cells.get_value(
            RECON_CUBE, f'{period},{version},{check},Input Total',
            dimensions=RECON_DIMS
        ) or 0
        output_total = tm1.cells.get_value(
            RECON_CUBE, f'{period},{version},{check},Output Total',
            dimensions=RECON_DIMS
        ) or 0
        status = tm1.cells.get_value(
            RECON_CUBE, f'{period},{version},{check},Status',
            dimensions=RECON_DIMS
        ) or 'NO DATA'
        results[check] = {
            'input':  input_total,
            'output': output_total,
            'status': status,
        }
    return results


def _gate_check(tm1, period, version, force=False):
    """Check VAL results — return True if safe to proceed."""
    print(f"\n  Validation gate check...")
    val_results = _read_val_status(tm1, period, version)
    all_pass = True
    for check, r in val_results.items():
        status  = r['status']
        message = r['message']
        icon    = '✓' if status == 'PASS' else ('!' if status == 'WARNING' else '✗')
        print(f"    {icon} {check}: {status} — {message}")
        if status == 'FAIL':
            all_pass = False

    if not all_pass and not force:
        print(f"\n  ✗ Validation failed — apportionment aborted.")
        print(f"    Run with --force to override gate check.")
        return False
    return True


def _run_stage1b(tm1, period, version, max_iter):
    """Stage 1b — Pool → Pool reciprocal iteration.

    Reads pool balances from Stage 1 and P2P driver percentages from TM1.
    Iterates until settled amounts converge within 0.01 tolerance.
    Writes settled amounts to CST Pool to Activity Apportionment (Settled Amount).
    Writes inter-pool transfers to CST Pool to Pool Apportionment (Apportioned Amount).
    """
    print(f"\n  Stage 1b — Pool → Pool (reciprocal)")

    TOLERANCE = 0.01

    P2P_CONFIG_CUBE = 'CST Pool to Pool Config'
    P2P_CONFIG_DIMS = ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Cost Pool Dest',
                       'GBL Cost Centre', 'CST Pool to Pool Config Measure']

    POOL_APR_CUBE = 'CST Account to Pool Apportionment'
    POOL_APR_DIMS = ['GBL Period', 'GBL Version', 'CST Cost Pool', 'GBL Cost Centre',
                     'GBL Account', 'CST Account to Pool Apportionment Measure']

    P2A_CUBE = 'CST Pool to Activity Apportionment'
    P2A_DIMS = ['GBL Period', 'GBL Version', 'CST Activity', 'CST Cost Pool',
                'GBL Cost Centre', 'CST Pool to Activity Apportionment Measure']

    P2P_APR_CUBE = 'CST Pool to Pool Config'
    P2P_APR_DIMS = ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Cost Pool Dest',
                    'GBL Cost Centre', 'CST Pool to Pool Config Measure']

    # ── 1. Read P2P driver values from TM1 ───────────────────────────────────
    mdx = (
        f"SELECT {{[CST Cost Pool].[Total Cost Pools]}} ON 0, "
        f"{{[CST Cost Pool Dest].[Total Cost Pools]}} ON 1 "
        f"FROM [{P2P_CONFIG_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Driver Value])"
    )
    # Read leaf-level P2P driver values
    p2p_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool Dest])}}, 0)}} ON 1 "
        f"FROM [{P2P_CONFIG_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Driver Value])"
    )
    raw = tm1.cells.execute_mdx(p2p_mdx, skip_zeros=True, element_unique_names=False)

    # Build pct[source_pool][dest_pool] — normalise driver values to percentages
    # With element_unique_names=False, key = full dimension tuple
    # CST Pool to Pool Config dims: Period(0), Version(1), Cost Pool(2), Cost Pool Dest(3), CC(4), Measure(5)
    raw_values = {}
    for key, cell in raw.items():
        src  = key[2]
        dest = key[3]
        val  = cell.get('Value') or 0
        if val != 0:
            raw_values.setdefault(src, {})[dest] = val

    if not raw_values:
        print(f"    ~ No P2P driver values found — skipping")
        return

    # Normalise to percentages per source pool
    pct = {}
    for src, dests in raw_values.items():
        total = sum(dests.values())
        if total > 0:
            pct[src] = {dest: val / total for dest, val in dests.items()}

    print(f"    P2P config: {len(pct)} source pools")

    # ── 2. Read Stage 1 pool balances from TM1 ───────────────────────────────
    bal_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([GBL Cost Centre])}}, 0)}} ON 1 "
        f"FROM [{POOL_APR_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Account].[{OVERHEAD_CONSOLIDATION}], "
        f"[CST Account to Pool Apportionment Measure].[Apportioned Amount])"
    )
    raw_bal = tm1.cells.execute_mdx(bal_mdx, skip_zeros=True, element_unique_names=False)

    # Keep per (pool, cc) amounts AND aggregate totals per pool
    # CST Account to Pool dims: Period(0), Version(1), Cost Pool(2), CC(3), Account(4), Measure(5)
    balances_by_cc = {}  # {(pool, cc): amount}
    balances = {}        # {pool: total}
    for key, cell in raw_bal.items():
        pool = key[2]
        cc   = key[3]
        val  = cell.get('Value') or 0
        balances_by_cc[(pool, cc)] = val
        balances[pool] = balances.get(pool, 0) + val

    all_pools = list(balances.keys())
    print(f"    Stage 1 balances: {len(all_pools)} pools  "
          f"total={sum(balances.values()):,.2f}")

    # ── 3. Iterate until convergence ─────────────────────────────────────────
    b = dict(balances)
    iterations = 0

    for i in range(max_iter):
        new_b = dict(balances)  # start from original each iteration
        for src, dests in pct.items():
            for dest, share in dests.items():
                new_b[dest] = new_b.get(dest, 0) + b.get(src, 0) * share

        max_change = max(abs(new_b.get(p, 0) - b.get(p, 0)) for p in set(list(b) + list(new_b)))
        b = new_b
        iterations += 1

        if max_change < TOLERANCE:
            break

    print(f"    Converged in {iterations} iterations  "
          f"(max change={max_change:.4f})")

    # ── 4. Write settled amounts to CST Pool to Activity Apportionment ────────
    # Use write_value per cell — handles GBL Period alias resolution correctly
    # Settled Amount per (pool, cc) — preserves Stage 1 CC distribution, scaled by P2P ratio
    # settled_net[pool] = throughput × (1 - % sent via P2P)
    settled_cells = {}
    settled_total = 0
    for pool, throughput in b.items():
        sent_pct     = sum(pct.get(pool, {}).values())
        settled_net  = throughput * (1 - sent_pct)
        pool_stage1  = balances.get(pool, 0)
        ratio        = (settled_net / pool_stage1) if pool_stage1 != 0 else 0
        # Write per CC, scaled by ratio — preserves CC distribution
        for (p, cc), stage1_cc in balances_by_cc.items():
            if p != pool:
                continue
            settled_cc = stage1_cc * ratio
            settled_cells[(period, version, 'Input', pool, cc, 'Settled Amount')] = settled_cc
            settled_total += settled_cc

    tm1.cells.write_values(P2A_CUBE, settled_cells, dimensions=P2A_DIMS)
    print(f"    ✓ Settled Amount written for {len(settled_cells)} pool/CC combinations  "
          f"total={settled_total:,.2f}")

    # ── 5. Write inter-pool transfers to CST Pool to Pool Apportionment ───────
    p2p_cells = {
        (period, version, src, dest, 'Input', 'Apportioned Amount'): b.get(src, 0) * share
        for src, dests in pct.items()
        for dest, share in dests.items()
    }
    tm1.cells.write_values(P2P_APR_CUBE, p2p_cells, dimensions=P2P_APR_DIMS)
    print(f"    ✓ Inter-pool transfers written: {len(p2p_cells)} pool pairs")

    # ── 6. Write Stage 1b Complete flag to Reconciliation cube ───────────────
    # Cross-cube flag read by the P2A Apportioned Amount rule to choose SA vs Amount.
    # Must be in a different cube — self-referential DB() consolidation reads return 0
    # during N: rule evaluation in the same cube.
    tm1.cells.write_values(
        RECON_CUBE,
        {(period, version, 'RC03', 'Stage 1b Complete'): 1},
        dimensions=RECON_DIMS,
    )
    print(f"    ✓ Stage 1b Complete flag written to Reconciliation cube")


def _run_stage2b(tm1, period, version, max_iter):
    """Stage 2b — Activity → Activity reciprocal iteration. Placeholder — not yet built."""
    print(f"\n  Stage 2b — Activity → Activity (reciprocal)")
    print(f"    ~ Not yet implemented — skipping")


def _print_rc_summary(rc_results):
    print(f"\n  Reconciliation summary:")
    all_pass = True
    for check, r in rc_results.items():
        status = r['status']
        icon   = '✓' if status == 'PASS' else ('?' if status == 'NO DATA' else '✗')
        print(f"    {icon} {check}: {status}  "
              f"In={r['input']:>14,.2f}  Out={r['output']:>14,.2f}")
        if status == 'FAIL':
            all_pass = False
    return all_pass


def _run_period(tm1, period, version, max_iter, force):
    """Run apportionment for a single period. Returns True if RC checks pass."""
    print(f"\n{'─'*60}")
    print(f"  CST Apportionment Run")
    print(f"  Period:  {period}")
    print(f"  Version: {version}")
    print(f"{'─'*60}")

    # Gate check
    if not _gate_check(tm1, period, version, force):
        print(f"\n  Skipping period {period} — gate check failed.")
        return False

    # Stage 1b — Pool → Pool reciprocal
    _run_stage1b(tm1, period, version, max_iter)

    # Stage 2b — Activity → Activity reciprocal
    _run_stage2b(tm1, period, version, max_iter)

    # Read RC results — rules fire on demand
    print(f"\n  Reading reconciliation checks...")
    rc_results = _read_rc_results(tm1, period, version)
    all_pass   = _print_rc_summary(rc_results)

    print(f"\n{'─'*60}")
    if all_pass:
        print(f"  ✓ Apportionment complete — all RC checks PASS")
    else:
        print(f"  ✗ Apportionment complete — RC checks FAILED, review in PAW")
    print(f"{'─'*60}\n")

    return all_pass


def main(period=None, version='Budget', max_iter=100, force=False):
    with get_tm1_service() as tm1:

        periods = [period] if period else get_version_periods(tm1, version)

        failed = []
        for p in periods:
            ok = _run_period(tm1, p, version, max_iter, force)
            if not ok:
                failed.append(p)

    if failed:
        print(f"\n  ✗ Periods with failures: {', '.join(failed)}")
        sys.exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--period',   default=None,
                        help='Single period e.g. 2025-04. Omit to run all periods for the version.')
    parser.add_argument('--version',  default='Budget')
    parser.add_argument('--max-iter', type=int, default=100)
    parser.add_argument('--force',    action='store_true',
                        help='Skip VAL gate check and run apportionment anyway')
    args = parser.parse_args()
    main(args.period, args.version, args.max_iter, args.force)
