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
from etl.val_checks import (
    run_val00,
    run_val01,
    run_val02,
    run_val03,
    run_val04,
    run_val05,
    run_val06,
)


OVERHEAD_CONSOLIDATION = CST_CONFIG["overhead_consolidation"]

RECON_CUBE = "CST Apportionment Reconciliation"
RECON_DIMS = [
    "GBL Period",
    "GBL Version",
    "CST Reconciliation Check",
    "CST Apportionment Reconciliation Measure",
]

VAL_CHECKS = ["VAL00", "VAL01", "VAL02", "VAL03", "VAL04", "VAL05"]
RC_CHECKS = ["RC01", "RC02", "RC03", "RC04", "RC05", "RC06"]


def _read_val_status(tm1, period, version):
    """Read all VAL check statuses from Reconciliation cube."""
    results = {}
    for check in VAL_CHECKS:
        try:
            status = (
                tm1.cells.get_value(
                    RECON_CUBE,
                    f"{period},{version},{check},Status",
                    dimensions=RECON_DIMS,
                )
                or "NO DATA"
            )
        except StopIteration:
            status = "NO DATA"

        try:
            message = (
                tm1.cells.get_value(
                    RECON_CUBE,
                    f"{period},{version},{check},Message",
                    dimensions=RECON_DIMS,
                )
                or ""
            )
        except StopIteration:
            message = ""

        results[check] = {"status": status, "message": message}
    return results


def _write_val_check(tm1, period, version, check, status, message=""):
    """Write VAL check status and message to Reconciliation cube."""
    tm1.cells.write_value(
        status,
        RECON_CUBE,
        (period, version, check, "Status"),
        dimensions=RECON_DIMS,
    )
    if message:
        tm1.cells.write_value(
            message,
            RECON_CUBE,
            (period, version, check, "Message"),
            dimensions=RECON_DIMS,
        )


def _read_rc_results(tm1, period, version):
    """Read RC check results from Reconciliation cube."""
    results = {}
    for check in RC_CHECKS:
        input_total = (
            tm1.cells.get_value(
                RECON_CUBE,
                f"{period},{version},{check},Input Total",
                dimensions=RECON_DIMS,
            )
            or 0
        )
        output_total = (
            tm1.cells.get_value(
                RECON_CUBE,
                f"{period},{version},{check},Output Total",
                dimensions=RECON_DIMS,
            )
            or 0
        )
        status = (
            tm1.cells.get_value(
                RECON_CUBE, f"{period},{version},{check},Status", dimensions=RECON_DIMS
            )
            or "NO DATA"
        )
        results[check] = {
            "input": input_total,
            "output": output_total,
            "status": status,
        }
    return results


def _gate_check(tm1, period, version, force=False):
    """Check VAL results — return True if safe to proceed."""
    print(f"\n  Validation gate check...")

    # Run VAL checks from val_checks.py (VAL00 first — fundamental config)
    run_val00(tm1, period, version)
    run_val01(tm1, period, version)
    run_val02(tm1, period, version)
    run_val03(tm1, period, version)
    run_val04(tm1, period, version)
    run_val05(tm1, period, version)
    run_val06(tm1, period, version)  # Date/Time stamp

    val_results = _read_val_status(tm1, period, version)
    all_pass = True
    for check, r in val_results.items():
        status = r["status"]
        message = r["message"]
        icon = "✓" if status == "PASS" else ("!" if status == "WARNING" else "✗")
        print(f"    {icon} {check}: {status} — {message}")
        if status == "FAIL":
            all_pass = False

    if not all_pass and not force:
        print(f"\n  ✗ Validation failed — apportionment aborted.")
        print(f"    Run with --force to override gate check.")
        return False
    return True


def _run_stage1b(tm1, period, version, max_iter):
    """Stage 1b — Pool → Pool reciprocal iteration.

    Reads pool balances from Stage 1, P2P driver percentages and Redistribution
    Percentage from TM1. Iterates until settled amounts converge within tolerance.
    Writes Base Amount + Final Balance to P2P Config cube (Apportioned Amount is rule-driven).
    Writes Settled Amount to CST Pool to Activity Apportionment.
    """
    print(f"\n  Stage 1b — Pool → Pool (reciprocal)")

    TOLERANCE = 0.01

    P2P_CONFIG_CUBE = "CST Pool to Pool Config"
    P2P_CONFIG_DIMS = [
        "GBL Period",
        "GBL Version",
        "CST Cost Pool",
        "CST Cost Pool Dest",
        "GBL Cost Centre",
        "CST Pool to Pool Config Measure",
    ]

    POOL_APR_CUBE = "CST Account to Pool Apportionment"
    POOL_APR_DIMS = [
        "GBL Period",
        "GBL Version",
        "CST Cost Pool",
        "GBL Cost Centre",
        "GBL Account",
        "CST Account to Pool Apportionment Measure",
    ]

    P2A_CUBE = "CST Pool to Activity Apportionment"
    P2A_DIMS = [
        "GBL Period",
        "GBL Version",
        "CST Activity",
        "CST Cost Pool",
        "GBL Cost Centre",
        "CST Pool to Activity Apportionment Measure",
    ]

    # ── 1. Read P2P driver values from TM1 ───────────────────────────────────
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

    # Build pct[source_pool][dest_pool] — normalised split of redistributed amount
    raw_values = {}
    for key, cell in raw.items():
        src = key[2]
        dest = key[3]
        val = cell.get("Value") or 0
        if val != 0:
            raw_values.setdefault(src, {})[dest] = val

    if not raw_values:
        print(f"    ~ No P2P driver values found — skipping")
        return

    pct = {}
    for src, dests in raw_values.items():
        total = sum(dests.values())
        if total > 0:
            pct[src] = {dest: val / total for dest, val in dests.items()}

    # ── 2. Read Redistribution Percentage per source pool ────────────────────
    redist_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{[CST Cost Pool Dest].[Input]}} ON 1 "
        f"FROM [{P2P_CONFIG_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Redistribution Percentage])"
    )
    raw_redist = tm1.cells.execute_mdx(
        redist_mdx, skip_zeros=True, element_unique_names=False
    )

    redist_pct = {}
    for key, cell in raw_redist.items():
        pool = key[2]
        val = cell.get("Value") or 0
        if val != 0:
            redist_pct[pool] = val / 100

    print(
        f"    P2P config: {len(pct)} source pools  {len(redist_pct)} with redistribution %"
    )

    # ── 3. Read Stage 1 pool balances from TM1 ───────────────────────────────
    bal_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([GBL Cost Centre])}}, 0)}} ON 1 "
        f"FROM [{POOL_APR_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Account].[{OVERHEAD_CONSOLIDATION}], "
        f"[CST Account to Pool Apportionment Measure].[Apportioned Amount])"
    )
    raw_bal = tm1.cells.execute_mdx(
        bal_mdx, skip_zeros=True, element_unique_names=False
    )

    balances_by_cc = {}  # {(pool, cc): amount}
    balances = {}  # {pool: total}
    for key, cell in raw_bal.items():
        pool = key[2]
        cc = key[3]
        val = cell.get("Value") or 0
        balances_by_cc[(pool, cc)] = val
        balances[pool] = balances.get(pool, 0) + val

    print(
        f"    Stage 1 balances: {len(balances)} pools  "
        f"total={sum(balances.values()):,.2f}"
    )

    # ── 4. Iterate until convergence ─────────────────────────────────────────
    b = dict(balances)
    iterations = 0

    for i in range(max_iter):
        new_b = dict(balances)
        for src, dests in pct.items():
            r = redist_pct.get(src, 0.0)
            if r == 0.0:
                raise ValueError(f"Missing redistribution % for pool: {src}")
            for dest, share in dests.items():
                new_b[dest] = new_b.get(dest, 0) + b.get(src, 0) * r * share

        max_change = max(
            abs(new_b.get(p, 0) - b.get(p, 0)) for p in set(list(b) + list(new_b))
        )
        b = new_b
        iterations += 1

        if max_change < TOLERANCE:
            break

    print(f"    Converged in {iterations} iterations  (max change={max_change:.4f})")

    # ── 5. Write Base Amount and Final Balance to P2P Config cube ─────────────
    # Clear existing cells for these measures
    clear_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool Dest])}}, 0)}} ON 1 "
        f"FROM [{P2P_CONFIG_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Base Amount])"
    )
    raw_clear = tm1.cells.execute_mdx(
        clear_mdx, skip_zeros=True, element_unique_names=False
    )
    if raw_clear:
        clear_cells = {
            (period, version, key[2], key[3], "Input", "Base Amount"): 0
            for key in raw_clear.keys()
        }
        tm1.cells.write_values(P2P_CONFIG_CUBE, clear_cells, dimensions=P2P_CONFIG_DIMS)
        print(f"    ✓ Cleared {len(clear_cells)} existing Base Amount cells")

    clear_mdx2 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool Dest])}}, 0)}} ON 1 "
        f"FROM [{P2P_CONFIG_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Final Balance])"
    )
    raw_clear2 = tm1.cells.execute_mdx(
        clear_mdx2, skip_zeros=True, element_unique_names=False
    )
    if raw_clear2:
        clear_cells2 = {
            (period, version, key[2], key[3], "Input", "Final Balance"): 0
            for key in raw_clear2.keys()
        }
        tm1.cells.write_values(
            P2P_CONFIG_CUBE, clear_cells2, dimensions=P2P_CONFIG_DIMS
        )
        print(f"    ✓ Cleared {len(clear_cells2)} existing Final Balance cells")

    config_cells = {}
    for pool, base in balances.items():
        config_cells[(period, version, pool, "Input", "Input", "Base Amount")] = base
        config_cells[(period, version, pool, "Input", "Input", "Final Balance")] = (
            b.get(pool, base)
        )
    tm1.cells.write_values(P2P_CONFIG_CUBE, config_cells, dimensions=P2P_CONFIG_DIMS)
    print(f"    ✓ Base Amount and Final Balance written for {len(balances)} pools")

    # ── 6. Write settled amounts to CST Pool to Activity Apportionment ────────
    settled_cells = {}
    settled_total = 0
    for pool, throughput in b.items():
        r = redist_pct.get(pool, 0.0)  # EDIT: changed default from 1.0 to 0.0
        # Explanation: Pools with no P2P config should keep 100% (redistribute 0%)
        settled_net = throughput * (1 - r)
        pool_stage1 = balances.get(pool, 0)
        ratio = (settled_net / pool_stage1) if pool_stage1 != 0 else 0
        for (p, cc), stage1_cc in balances_by_cc.items():
            if p != pool:
                continue
            settled_cc = stage1_cc * ratio
            settled_cells[(period, version, "Input", pool, cc, "Settled Amount")] = (
                settled_cc
            )
            settled_total += settled_cc

    # Clear existing Settled Amount cells then write new ones
    if settled_cells:
        clear_cells = {k: 0 for k in settled_cells}
        tm1.cells.write_values(P2A_CUBE, clear_cells, dimensions=P2A_DIMS)
        print(f"    ✓ Cleared {len(clear_cells)} existing Settled Amount cells")

    tm1.cells.write_values(P2A_CUBE, settled_cells, dimensions=P2A_DIMS)
    print(
        f"    ✓ Settled Amount written for {len(settled_cells)} pool/CC combinations  "
        f"total={settled_total:,.2f}"
    )

    # ── 7. Write Stage 1b Complete flag to Reconciliation cube ────────────────
    # Clear existing flag
    tm1.cells.write_values(
        RECON_CUBE,
        {(period, version, "RC03", "Stage 1b Complete"): 0},
        dimensions=RECON_DIMS,
    )
    # Write new flag
    tm1.cells.write_values(
        RECON_CUBE,
        {(period, version, "RC03", "Stage 1b Complete"): 1},
        dimensions=RECON_DIMS,
    )
    print(f"    ✓ Stage 1b Complete flag written to Reconciliation cube")


def _run_stage2b(tm1, period, version, max_iter):
    """Stage 2b — Activity → Activity reciprocal iteration.

    Mirrors _run_stage1b structure exactly, substituting Activity dimensions.
    Reads driver values and redistribution % from CST Activity to Activity Config.
    Writes Base Amount + Final Balance to A2A Config, Settled Amount to A2SL cube.
    """
    print(f"\n  Stage 2b — Activity → Activity (reciprocal)")

    TOLERANCE = 0.01

    A2A_CONFIG_CUBE = 'CST Activity to Activity Config'
    A2A_CONFIG_DIMS = ['GBL Period', 'GBL Version', 'CST Activity', 'CST Activity Dest',
                       'GBL Cost Centre', 'CST Activity to Activity Config Measure']

    P2A_CUBE = 'CST Pool to Activity Apportionment'
    P2A_DIMS = ['GBL Period', 'GBL Version', 'CST Activity', 'CST Cost Pool',
                'GBL Cost Centre', 'CST Pool to Activity Apportionment Measure']

    A2SL_CUBE = 'CST Activity to Service Line Apportionment'
    A2SL_DIMS = ['GBL Period', 'GBL Version', 'CST Service Line', 'CST Activity',
                 'GBL Cost Centre', 'CST Activity to Service Line Apportionment Measure']

    # ── 1. Read A2A driver values ─────────────────────────────────────────────
    # A2A_CONFIG dims: Period(0), Version(1), Activity(2), ActivityDest(3), CC(4), Measure(5)
    a2a_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity Dest])}}, 0)}} ON 1 "
        f"FROM [{A2A_CONFIG_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Activity to Activity Config Measure].[Driver Value])"
    )
    raw = tm1.cells.execute_mdx(a2a_mdx, skip_zeros=True, element_unique_names=False)

    raw_values = {}
    for key, cell in raw.items():
        src  = key[2]
        dest = key[3]
        val  = cell.get('Value') or 0
        if val != 0:
            raw_values.setdefault(src, {})[dest] = val

    if not raw_values:
        print(f"    ~ No A2A driver values found — skipping")
        return

    pct = {}
    for src, dests in raw_values.items():
        total = sum(dests.values())
        if total > 0:
            pct[src] = {dest: val / total for dest, val in dests.items()}

    # ── 2. Read Redistribution Percentage per source activity ─────────────────
    # Stored at Activity Dest = 'Input'
    redist_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0, "
        f"{{[CST Activity Dest].[Input]}} ON 1 "
        f"FROM [{A2A_CONFIG_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Activity to Activity Config Measure].[Redistribution Percentage])"
    )
    raw_redist = tm1.cells.execute_mdx(redist_mdx, skip_zeros=True, element_unique_names=False)

    redist_pct = {}
    for key, cell in raw_redist.items():
        act = key[2]
        val = cell.get('Value') or 0
        if val != 0:
            redist_pct[act] = val / 100

    print(f"    A2A config: {len(pct)} source activities  {len(redist_pct)} with redistribution %")

    # ── 3. Read Stage 2 activity balances from P2A cube ──────────────────────
    # Fix CST Cost Pool at consolidation to get totals across all pools per activity/CC
    # P2A dims: Period(0), Version(1), Activity(2), CostPool(3), CC(4), Measure(5)
    bal_mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([GBL Cost Centre])}}, 0)}} ON 1 "
        f"FROM [{P2A_CUBE}] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Cost Pool].[Total Cost Pools], "
        f"[CST Pool to Activity Apportionment Measure].[Apportioned Amount])"
    )
    raw_bal = tm1.cells.execute_mdx(bal_mdx, skip_zeros=True, element_unique_names=False)

    balances_by_cc = {}  # {(activity, cc): amount}
    balances = {}        # {activity: total}
    for key, cell in raw_bal.items():
        act = key[2]
        cc  = key[4]
        val = cell.get('Value') or 0
        balances_by_cc[(act, cc)] = balances_by_cc.get((act, cc), 0) + val
        balances[act] = balances.get(act, 0) + val

    if not balances:
        print(f"    ~ No Stage 2 balances found — skipping")
        return

    print(f"    Stage 2 balances: {len(balances)} activities  "
          f"total={sum(balances.values()):,.2f}")

    # ── 4. Iterate until convergence ─────────────────────────────────────────
    b = dict(balances)
    iterations = 0

    for i in range(max_iter):
        new_b = dict(balances)
        for src, dests in pct.items():
            r = redist_pct.get(src, 0.0)
            if r == 0.0:
                raise ValueError(f"Missing redistribution % for activity: {src}")
            for dest, share in dests.items():
                new_b[dest] = new_b.get(dest, 0) + b.get(src, 0) * r * share

        max_change = max(abs(new_b.get(p, 0) - b.get(p, 0)) for p in set(list(b) + list(new_b)))
        b = new_b
        iterations += 1

        if max_change < TOLERANCE:
            break

    print(f"    Converged in {iterations} iterations  (max change={max_change:.4f})")

    # ── 5. Write Base Amount and Final Balance to A2A Config cube ─────────────
    # Stored at Activity Dest = 'Input' — Apportioned Amount is rule-driven
    # Activities with no A2A config get Final Balance = Base Amount
    config_cells = {}
    for act, base in balances.items():
        config_cells[(period, version, act, 'Input', 'Input', 'Base Amount')]   = base
        config_cells[(period, version, act, 'Input', 'Input', 'Final Balance')] = b.get(act, base)
    tm1.cells.write_values(A2A_CONFIG_CUBE, config_cells, dimensions=A2A_CONFIG_DIMS)
    print(f"    ✓ Base Amount and Final Balance written for {len(balances)} activities")

    # ── 6. Write settled amounts to CST Activity to Service Line Apportionment ─
    # settled_net = final balance × (1 - redistribution %) — flows forward to Stage 3
    settled_cells = {}
    settled_total = 0
    for act, throughput in b.items():
        r           = redist_pct.get(act, 0.0)
        settled_net = throughput * (1 - r)
        act_stage2  = balances.get(act, 0)
        ratio       = (settled_net / act_stage2) if act_stage2 != 0 else 0
        for (a, cc), stage2_cc in balances_by_cc.items():
            if a != act:
                continue
            settled_cc = stage2_cc * ratio
            settled_cells[(period, version, 'Input', act, cc, 'Settled Amount')] = settled_cc
            settled_total += settled_cc

    tm1.cells.write_values(A2SL_CUBE, settled_cells, dimensions=A2SL_DIMS)
    print(f"    ✓ Settled Amount written for {len(settled_cells)} activity/CC combinations  "
          f"total={settled_total:,.2f}")

    # ── 7. Write Stage 2b Complete flag to Reconciliation cube ───────────────
    tm1.cells.write_values(
        RECON_CUBE,
        {(period, version, 'RC04', 'Stage 2b Complete'): 1},
        dimensions=RECON_DIMS,
    )
    print(f"    ✓ Stage 2b Complete flag written to Reconciliation cube")


def _print_rc_summary(rc_results):
    print(f"\n  Reconciliation summary:")
    all_pass = True
    for check, r in rc_results.items():
        status = r["status"]
        icon = "✓" if status == "PASS" else ("?" if status == "NO DATA" else "✗")
        print(
            f"    {icon} {check}: {status}  "
            f"In={r['input']:>14,.2f}  Out={r['output']:>14,.2f}"
        )
        if status == "FAIL":
            all_pass = False
    return all_pass


def _run_period(tm1, period, version, max_iter, force):
    """Run apportionment for a single period. Returns True if RC checks pass."""
    print(f"\n{'─' * 60}")
    print(f"  CST Apportionment Run")
    print(f"  Period:  {period}")
    print(f"  Version: {version}")
    print(f"{'─' * 60}")

    if not _gate_check(tm1, period, version, force):
        print(f"\n  Skipping period {period} — gate check failed.")
        return False

    _run_stage1b(tm1, period, version, max_iter)
    _run_stage2b(tm1, period, version, max_iter)

    print(f"\n  Reading reconciliation checks...")
    rc_results = _read_rc_results(tm1, period, version)
    all_pass = _print_rc_summary(rc_results)

    print(f"\n{'─' * 60}")
    if all_pass:
        print(f"  ✓ Apportionment complete — all RC checks PASS")
    else:
        print(f"  ✗ Apportionment complete — RC checks FAILED, review in PAW")
    print(f"{'─' * 60}\n")

    return all_pass


def main(period=None, version="Budget", max_iter=100, force=False):
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period",
        default=None,
        help="Single period e.g. 2025-04. Omit to run all periods for the version.",
    )
    parser.add_argument("--version", default="Budget")
    parser.add_argument("--max-iter", type=int, default=100)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip VAL gate check and run apportionment anyway",
    )
    args = parser.parse_args()
    main(args.period, args.version, args.max_iter, args.force)
