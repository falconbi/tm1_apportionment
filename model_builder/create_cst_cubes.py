"""
create_cst_cubes.py
Creates all CST cubes (10 cubes).
Called by build_cst_model.py.
"""

import sys
sys.path.insert(0, '.')
from TM1py.Objects import Cube
from tm1py_connect import get_tm1_service
from gbl_check import verify_gbl


CUBES = [
    # ── Stage 1: Account → Pool ───────────────────────────────────────────────
    (
        'CST Account Config',
        ['GBL Period', 'GBL Version', 'GBL Account', 'GBL Cost Centre', 'CST Cost Pool',
         'CST Account Config Measure'],
    ),
    (
        'CST Account to Pool Apportionment',
        ['GBL Period', 'GBL Version', 'CST Cost Pool', 'GBL Cost Centre', 'GBL Account',
         'CST Account to Pool Apportionment Measure'],
    ),
    # ── Stage 1b: Pool → Pool (reciprocal) ───────────────────────────────────
    (
        'CST Pool to Pool Config',
        ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Cost Pool Dest', 'GBL Cost Centre',
         'CST Pool to Pool Config Measure'],
    ),
    # ── Stage 2: Pool → Activity ─────────────────────────────────────────────
    (
        'CST Pool Config',
        ['GBL Period', 'GBL Version', 'CST Cost Pool', 'CST Driver', 'CST Activity',
         'CST Pool Config Measure'],
    ),
    (
        'CST Pool to Activity Apportionment',
        ['GBL Period', 'GBL Version', 'CST Activity', 'CST Cost Pool', 'GBL Cost Centre',
         'CST Pool to Activity Apportionment Measure'],
    ),
    # ── Stage 2b: Activity → Activity (reciprocal) ───────────────────────────
    (
        'CST Activity to Activity Config',
        ['GBL Period', 'GBL Version', 'CST Activity', 'CST Activity Dest', 'GBL Cost Centre',
         'CST Activity to Activity Config Measure'],
    ),
    # ── Stage 3: Activity → Service Line ─────────────────────────────────────
    (
        'CST Activity Config',
        ['GBL Period', 'GBL Version', 'CST Activity', 'CST Driver', 'CST Service Line',
         'CST Activity Config Measure'],
    ),
    (
        'CST Activity to Service Line Apportionment',
        ['GBL Period', 'GBL Version', 'CST Service Line', 'CST Activity', 'GBL Cost Centre',
         'CST Activity to Service Line Apportionment Measure'],
    ),
    # ── ETL Control ───────────────────────────────────────────────────────────
    (
        'CST ETL Control',
        ['CST ETL Job', 'CST ETL Control Measure'],
    ),
    # ── Output / Audit ────────────────────────────────────────────────────────
    (
        'CST Profit and Loss Report',
        ['GBL Period', 'GBL Version', 'GBL Account', 'CST Service Line', 'GBL Cost Centre',
         'CST Apportionment Stage', 'CST Profit and Loss Report Measure'],
    ),
    (
        'CST Apportionment Reconciliation',
        ['GBL Period', 'GBL Version', 'CST Reconciliation Check',
         'CST Apportionment Reconciliation Measure'],
    ),
]


def main(tm1):
    print(f"\n{'─'*60}")
    print("  Creating CST cubes...")
    print(f"{'─'*60}")

    for cube_name, dimensions in CUBES:
        missing = [d for d in dimensions if not tm1.dimensions.exists(d)]
        if missing:
            print(f"\n  ✗ Cannot create '{cube_name}' — missing dimension(s):")
            for d in missing:
                print(f"      - {d}")
            print(f"\n  Run create_cst_dimensions.py first.")
            sys.exit(1)
        if tm1.cubes.exists(cube_name):
            tm1.cubes.delete(cube_name)
        cube = Cube(cube_name, dimensions)
        tm1.cubes.create(cube)
        print(f"  ✓ {cube_name}")

    print(f"  ✓ All {len(CUBES)} CST cubes created.")


if __name__ == '__main__':
    tm1 = get_tm1_service()
    verify_gbl(tm1)
    main(tm1)
    tm1.logout()
