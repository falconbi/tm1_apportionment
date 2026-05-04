"""
etl/val_checks.py
Pre-flight VAL checks for CST Apportionment.
Can run standalone: python3 etl/val_checks.py --period 2026-04 --version Budget
Or be called from run_apportionment.py gate check.

Writes VAL01-VAL06 status + message to CST Apportionment Reconciliation cube.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tm1py_connect import get_tm1_service
from config import CST_CONFIG
from etl.utils import get_version_periods

RECON_CUBE = "CST Apportionment Reconciliation"
RECON_DIMS = [
    "GBL Period",
    "GBL Version",
    "CST Reconciliation Check",
    "CST Apportionment Reconciliation Measure",
]


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


def run_val00(tm1, period, version):
    """VAL00: No accounts with blank Apportionment Type (run first).
    Check at GBL Cost Centre=INPUT, CST Cost Pool=INPUT, CST Service Line=INPUT."""
    print("  VAL00: Checking no accounts with blank Apportionment Type...")

    # Get all leaf accounts from dimension
    all_accounts = tm1.elements.get_leaf_elements("GBL Account", "GBL Account")
    accounts = [e.name for e in all_accounts]

    blank = []
    for acc in accounts:
        try:
            val = tm1.cells.get_value(
                "CST Account Config",
                f"{period},{version},{acc},Input,Input,Input,Apportionment Type",
                dimensions=[
                    "GBL Period",
                    "GBL Version",
                    "GBL Account",
                    "GBL Cost Centre",
                    "CST Cost Pool",
                    "CST Service Line",
                    "CST Account Config Measure",
                ],
            )
            if not val or val == "":
                blank.append(acc)
        except StopIteration:
            # Cell never written - blank
            blank.append(acc)

    if blank:
        msg = f"{len(blank)} accounts with blank Apportionment Type"
        status = "FAIL"
    else:
        msg = "No accounts with blank Apportionment Type"
        status = "PASS"

    _write_val_check(tm1, period, version, "VAL00", status, msg)
    return status


def run_val01(tm1, period, version):
    """VAL01: All Indirect accounts have CP% = 100% in Account Config."""
    print("  VAL01: Checking all Indirect accounts have CP% = 100%...")

    # Query Account Config for Indirect accounts with CP% != 100
    mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([GBL Account])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([GBL Cost Centre])}}, 0)}} ON 1 "
        f"FROM [CST Account Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Account Config Measure].[Driver Percentage Share])"
    )
    raw = tm1.cells.execute_mdx(mdx, skip_zeros=True, element_unique_names=False)

    # Check which accounts have sum != 100
    account_sums = {}
    for key, cell in raw.items():
        acc = key[2]
        val = cell.get("Value") or 0
        account_sums[acc] = account_sums.get(acc, 0) + val

    # Filter for Indirect/Excluded accounts (from Account Config)
    # For now, check all accounts
    failing = {acc: s for acc, s in account_sums.items() if abs(s - 100) > 0.01}

    if failing:
        msg = f"{len(failing)} accounts with CP% != 100%"
        status = "FAIL"
    else:
        msg = "All Indirect accounts have CP% = 100%"
        status = "PASS"

    _write_val_check(tm1, period, version, "VAL01", status, msg)
    return status


def run_val02(tm1, period, version):
    """VAL02: Pool→Pool — Check Active pairs have Redistribution% >0,
    Driver assigned, and Driver Values exist."""
    print("  VAL02: Checking Pool→Pool config (Active, Driver, Values)...")

    errors = []

    # Get all active CP→CP_Dest pairs (Active=1 at CC=Input)
    mdx_active = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool Dest])}}, 0)}} ON 1 "
        f"FROM [CST Pool to Pool Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Active])"
    )
    active_raw = tm1.cells.execute_mdx(
        mdx_active, skip_zeros=False, element_unique_names=False
    )
    active_pairs = {k: c.get("Value") or 0 for k, c in active_raw.items()}
    active_cp_dest = {k: v for k, v in active_pairs.items() if v == 1}

    if not active_cp_dest:
        _write_val_check(tm1, period, version, "VAL02", "PASS", "No active P2P pairs")
        return "PASS"

    # Get unique Cost Pools that have active pairs
    active_cps = set(k[2] for k in active_cp_dest.keys())

    # Check 1: Redistribution% > 0 (at CP_Dest=Input, CC=Input)
    mdx_redist = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0 "
        f"FROM [CST Pool to Pool Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Cost Pool Dest].[Input], [GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Redistribution Percentage])"
    )
    redist_raw = tm1.cells.execute_mdx(
        mdx_redist, skip_zeros=False, element_unique_names=False
    )
    redist_vals = {k[2]: c.get("Value") or 0 for k, c in redist_raw.items()}

    missing_redist = [cp for cp in active_cps if redist_vals.get(cp, 0) <= 0]
    if missing_redist:
        errors.append(f"{len(missing_redist)} pools missing Redistribution%")

    # Check 2: Driver assigned (at CP_Dest=Input, CC=Input)
    mdx_driver = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0 "
        f"FROM [CST Pool to Pool Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Cost Pool Dest].[Input], [GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Driver Description])"
    )
    driver_raw = tm1.cells.execute_mdx(
        mdx_driver, skip_zeros=False, element_unique_names=False
    )
    driver_vals = {k[2]: (c.get("Value") or "").strip() for k, c in driver_raw.items()}

    missing_driver = [cp for cp in active_cps if not driver_vals.get(cp, "")]
    if missing_driver:
        errors.append(f"{len(missing_driver)} pools missing Driver")

    # Check 3: Driver Values exist (at actual CP_Dest codes, CC=Input)
    mdx_dv = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool Dest])}}, 0)}} ON 1 "
        f"FROM [CST Pool to Pool Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Pool to Pool Config Measure].[Driver Value])"
    )
    dv_raw = tm1.cells.execute_mdx(mdx_dv, skip_zeros=True, element_unique_names=False)
    driver_values = {(k[2], k[3]): c.get("Value") or 0 for k, c in dv_raw.items()}

    missing_dv = []
    for k in active_cp_dest.keys():
        cp, cp_dest = k[2], k[3]
        if driver_values.get((cp, cp_dest), 0) <= 0:
            missing_dv.append(f"{cp}→{cp_dest}")
    if missing_dv:
        errors.append(f"{len(missing_dv)} pairs missing Driver Value")

    if errors:
        msg = "; ".join(errors)
        status = "FAIL"
    else:
        msg = "Pool→Pool config valid"
        status = "PASS"

    _write_val_check(tm1, period, version, "VAL02", status, msg)
    return status


def run_val03(tm1, period, version):
    """VAL03: Pool→Activity — pools with values must have Driver, Driver has values."""
    print("  VAL03: Checking Pool→Activity config (Driver + values)...")

    # Step 1: Get pools with Driver Values > 0 (at CST Driver=INPUT, CST Activity=INPUT)
    mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0 "
        f"FROM [CST Pool Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Driver].[INPUT], [CST Activity].[INPUT], "
        f"[CST Pool Config Measure].[Driver Value])"
    )
    raw = tm1.cells.execute_mdx(mdx, skip_zeros=True, element_unique_names=False)
    pools_with_values = {k[2] for k, c in raw.items() if (c.get("Value") or 0) > 0}

    if not pools_with_values:
        _write_val_check(
            tm1, period, version, "VAL03", "PASS", "Pool→Activity config valid"
        )
        return "PASS"

    # Step 2: Get Driver Name for each pool (at CST Driver=INPUT, CST Activity=INPUT)
    mdx2 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Cost Pool])}}, 0)}} ON 0 "
        f"FROM [CST Pool Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Driver].[INPUT], [CST Activity].[INPUT], "
        f"[CST Pool Config Measure].[Pool to Activity Basis])"
    )
    driver_raw = tm1.cells.execute_mdx(
        mdx2, skip_zeros=False, element_unique_names=False
    )
    pool_drivers = {k[2]: (c.get("Value") or "").strip() for k, c in driver_raw.items()}

    # Check pools with values have a driver assigned
    missing_driver = [cp for cp in pools_with_values if not pool_drivers.get(cp, "")]
    if missing_driver:
        msg = f"{len(missing_driver)} pools with values missing Driver"
        _write_val_check(tm1, period, version, "VAL03", "FAIL", msg)
        return "FAIL"

    # Step 3: Check driver values exist for assigned drivers
    pool_filter = ",".join(f"[CST Cost Pool].[{cp}]" for cp in pools_with_values)
    mdx3 = (
        f"SELECT {{{pool_filter}}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Driver])}}, 0)}} ON 1, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 2 "
        f"FROM [CST Pool Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Pool Config Measure].[Driver Value])"
    )
    dv_raw = tm1.cells.execute_mdx(mdx3, skip_zeros=True, element_unique_names=False)

    pool_driver_has_values = set()
    for k, c in dv_raw.items():
        cp = k[2]
        driver = k[3]
        val = c.get("Value") or 0
        if val > 0:
            pool_driver_has_values.add((cp, driver))

    missing_dv = []
    for cp in pools_with_values:
        driver = pool_drivers.get(cp, "")
        if driver and (cp, driver) not in pool_driver_has_values:
            missing_dv.append(f"{cp}/{driver}")

    if missing_dv:
        msg = f"{len(missing_dv)} pool/driver combos missing Driver Values"
        status = "FAIL"
    else:
        msg = "Pool→Activity config valid"
        status = "PASS"

    _write_val_check(tm1, period, version, "VAL03", status, msg)
    return status


def run_val04(tm1, period, version):
    """VAL04: Activity→Activity — Check for config consistency.
    If activity has Redistribution% or Driver, it MUST have Driver Values.
    WARNING only (incomplete config, not a blocker)."""
    print("  VAL04: Checking Activity→Activity config consistency...")

    errors = []

    # Get activities with Redistribution% > 0 (at CST Activity Dest=INPUT, CC=Input)
    mdx1 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0 "
        f"FROM [CST Activity to Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Activity Dest].[INPUT], [GBL Cost Centre].[Input], "
        f"[CST Activity to Activity Config Measure].[Redistribution Percentage])"
    )
    redist_raw = tm1.cells.execute_mdx(
        mdx1, skip_zeros=False, element_unique_names=False
    )
    acts_with_redist = {
        k[2] for k, c in redist_raw.items() if (c.get("Value") or 0) > 0
    }

    # Get activities with Driver Description (at CST Activity Dest=INPUT, CC=Input)
    mdx2 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0 "
        f"FROM [CST Activity to Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Activity Dest].[INPUT], [GBL Cost Centre].[Input], "
        f"[CST Activity to Activity Config Measure].[Driver Description])"
    )
    driver_raw = tm1.cells.execute_mdx(
        mdx2, skip_zeros=False, element_unique_names=False
    )
    act_drivers = {k[2]: (c.get("Value") or "").strip() for k, c in driver_raw.items()}
    acts_with_driver = {act for act, driver in act_drivers.items() if driver}

    # Activities that claim to have A2A config (have Redistribution% or Driver)
    acts_claiming_a2a = acts_with_redist | acts_with_driver

    if not acts_claiming_a2a:
        _write_val_check(
            tm1, period, version, "VAL04", "PASS", "No activities with A2A config"
        )
        return "PASS"

    # Check these activities have Driver Values > 0 (at actual CST Activity Dest codes)
    mdx3 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity Dest])}}, 0)}} ON 1 "
        f"FROM [CST Activity to Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[GBL Cost Centre].[Input], "
        f"[CST Activity to Activity Config Measure].[Driver Value])"
    )
    dv_raw = tm1.cells.execute_mdx(mdx3, skip_zeros=True, element_unique_names=False)
    acts_with_dv = {k[2] for k, c in dv_raw.items() if (c.get("Value") or 0) > 0}

    # Activities claiming A2A but missing Driver Values
    missing_dv = acts_claiming_a2a - acts_with_dv
    if missing_dv:
        errors.append(f"{len(missing_dv)} activities with config but no Driver Values")

    if errors:
        msg = "; ".join(errors)
        status = "WARNING"
    else:
        msg = "Activity→Activity config valid"
        status = "PASS"

    _write_val_check(tm1, period, version, "VAL04", status, msg)
    return status

    # For activities with driver values, check they have Driver Description
    mdx2 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0 "
        f"FROM [CST Activity to Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Activity Dest].[INPUT], [GBL Cost Centre].[Input], "
        f"[CST Activity to Activity Config Measure].[Driver Description])"
    )
    driver_raw = tm1.cells.execute_mdx(
        mdx2, skip_zeros=False, element_unique_names=False
    )
    act_drivers = {k[2]: (c.get("Value") or "").strip() for k, c in driver_raw.items()}

    missing_driver = [act for act in acts_with_values if not act_drivers.get(act, "")]
    if missing_driver:
        msg = f"{len(missing_driver)} activities with values missing Driver"
        _write_val_check(tm1, period, version, "VAL04", "WARNING", msg)
        return "WARNING"

    # Check Redistribution% > 0
    mdx3 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0 "
        f"FROM [CST Activity to Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Activity Dest].[INPUT], [GBL Cost Centre].[Input], "
        f"[CST Activity to Activity Config Measure].[Redistribution Percentage])"
    )
    redist_raw = tm1.cells.execute_mdx(
        mdx3, skip_zeros=False, element_unique_names=False
    )
    redist_vals = {k[2]: c.get("Value") or 0 for k, c in redist_raw.items()}

    missing_redist = [act for act in acts_with_values if redist_vals.get(act, 0) <= 0]
    if missing_redist:
        msg = f"{len(missing_redist)} activities with values missing Redistribution%"
        _write_val_check(tm1, period, version, "VAL04", "WARNING", msg)
        return "WARNING"

    _write_val_check(
        tm1, period, version, "VAL04", "PASS", "Activity→Activity config valid"
    )
    return "PASS"


def run_val05(tm1, period, version):
    """VAL05: Activity→Service Line — Activities with values must have
    Driver assigned, Driver must have values."""
    print("  VAL05: Checking Activity→Service Line config (Driver + values)...")

    # Step 1: Get activities with Driver Values > 0 (at CST Driver=INPUT, CST Service Line=INPUT)
    mdx = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0 "
        f"FROM [CST Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Driver].[INPUT], [CST Service Line].[INPUT], "
        f"[CST Activity Config Measure].[Driver Value])"
    )
    raw = tm1.cells.execute_mdx(mdx, skip_zeros=True, element_unique_names=False)
    acts_with_values = {k[2] for k, c in raw.items() if (c.get("Value") or 0) > 0}

    if not acts_with_values:
        _write_val_check(
            tm1, period, version, "VAL05", "PASS", "Activity→Service Line config valid"
        )
        return "PASS"

    # Step 2: Get Driver Name for each activity (at CST Driver=INPUT, CST Service Line=INPUT)
    mdx2 = (
        f"SELECT "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Activity])}}, 0)}} ON 0 "
        f"FROM [CST Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Driver].[INPUT], [CST Service Line].[INPUT], "
        f"[CST Activity Config Measure].[Activity to Service Line Basis])"
    )
    driver_raw = tm1.cells.execute_mdx(
        mdx2, skip_zeros=False, element_unique_names=False
    )
    act_drivers = {k[2]: (c.get("Value") or "").strip() for k, c in driver_raw.items()}

    # Check activities with values have a driver assigned
    missing_driver = [act for act in acts_with_values if not act_drivers.get(act, "")]
    if missing_driver:
        msg = f"{len(missing_driver)} activities with values missing Driver"
        _write_val_check(tm1, period, version, "VAL05", "FAIL", msg)
        return "FAIL"

    # Step 3: Check driver values exist for assigned drivers
    act_filter = ",".join(f"[CST Activity].[{act}]" for act in acts_with_values)
    mdx3 = (
        f"SELECT {{{act_filter}}} ON 0, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Driver])}}, 0)}} ON 1, "
        f"{{TM1FILTERBYLEVEL({{TM1SUBSETALL([CST Service Line])}}, 0)}} ON 2 "
        f"FROM [CST Activity Config] "
        f"WHERE ([GBL Period].[{period}], [GBL Version].[{version}], "
        f"[CST Activity Config Measure].[Driver Value])"
    )
    dv_raw = tm1.cells.execute_mdx(mdx3, skip_zeros=True, element_unique_names=False)

    act_driver_has_values = set()
    for k, c in dv_raw.items():
        act = k[2]
        driver = k[3]
        val = c.get("Value") or 0
        if val > 0:
            act_driver_has_values.add((act, driver))

    missing_dv = []
    for act in acts_with_values:
        driver = act_drivers.get(act, "")
        if driver and (act, driver) not in act_driver_has_values:
            missing_dv.append(f"{act}/{driver}")

    if missing_dv:
        msg = f"{len(missing_dv)} activity/driver combos missing Driver Values"
        status = "FAIL"
    else:
        msg = "Activity→Service Line config valid"
        status = "PASS"

    _write_val_check(tm1, period, version, "VAL05", status, msg)
    return status


def run_val06(tm1, period, version):
    """VAL06: Write Date and Time Stamp when VAL checks complete."""
    print("  VAL06: Writing Date and Time Stamp...")

    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _write_val_check(tm1, period, version, "VAL06", "PASS", f"VAL checks run at {now}")
    return "PASS"


def run_val00(tm1, period, version):
    """VAL00: No accounts with blank Apportionment Type (run first).
    Check at GBL Cost Centre=INPUT, CST Cost Pool=INPUT, CST Service Line=INPUT."""
    print("  VAL00: Checking no accounts with blank Apportionment Type...")

    # Get all leaf accounts from dimension
    all_accounts = tm1.elements.get_leaf_elements("GBL Account", "GBL Account")
    accounts = [e.name for e in all_accounts]

    blank = []
    for acc in accounts:
        try:
            val = tm1.cells.get_value(
                "CST Account Config",
                f"{period},{version},{acc},Input,Input,Input,Apportionment Type",
                dimensions=[
                    "GBL Period",
                    "GBL Version",
                    "GBL Account",
                    "GBL Cost Centre",
                    "CST Cost Pool",
                    "CST Service Line",
                    "CST Account Config Measure",
                ],
            )
            if not val or val == "":
                blank.append(acc)
        except StopIteration:
            # Cell never written - blank
            blank.append(acc)

    if blank:
        msg = f"{len(blank)} accounts with blank Apportionment Type"
        status = "FAIL"
    else:
        msg = "No accounts with blank Apportionment Type"
        status = "PASS"

    _write_val_check(tm1, period, version, "VAL00", status, msg)
    return status


def run_all_val_checks(tm1, period, version):
    """Run all VAL checks. VAL00 runs first (fundamental config check)."""
    print(f"\n  Running VAL checks for {period}...")

    run_val00(tm1, period, version)  # Apportionment Type — run first
    run_val01(tm1, period, version)
    run_val02(tm1, period, version)
    run_val03(tm1, period, version)
    run_val04(tm1, period, version)
    run_val05(tm1, period, version)
    run_val06(tm1, period, version)  # Date/Time stamp

    print("  ✓ VAL00-VAL06 complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period",
        default=None,
        help="Single period e.g. 2026-04. Omit to run all periods for the version.",
    )
    parser.add_argument("--version", default="Budget")

    args = parser.parse_args()

    with get_tm1_service() as tm1:
        periods = (
            [args.period] if args.period else get_version_periods(tm1, args.version)
        )

        for p in periods:
            run_all_val_checks(tm1, p, args.version)
