"""
cleanup_cst_model.py
Deletes all CST module cubes and dimensions before a clean rebuild.
Does NOT touch GBL dimensions — those are managed by tm1_global.
Note: GBL Cost Centre Input sentinel is left in place (harmless if GBL rebuilds).

Run order:
  python3 model_builder/cleanup_cst_model.py
  python3 model_builder/build_cst_model.py
"""

import sys
sys.path.insert(0, '.')
from tm1py_connect import get_tm1_service

tm1 = get_tm1_service()

CUBES_TO_DELETE = [
    # Current 10-cube design
    'CST Account Config',
    'CST Account to Pool Apportionment',
    'CST Pool to Pool Config',
    'CST Pool Config',
    'CST Pool to Activity Apportionment',
    'CST Activity to Activity Config',
    'CST Activity Config',
    'CST Activity to Service Line Apportionment',
    'CST Profit and Loss Report',
    'CST Apportionment Reconciliation',
    # Legacy — 22-cube design
    'CST Account Input',
    'CST Account Driver Config',
    'CST Account Flag',
    'CST Account to Pool Driver Pct',
    'CST Pool to Pool Apportionment',
    'CST Pool to Pool Driver Pct',
    'CST Pool to Pool Driver Values',
    'CST Pool Driver Config',
    'CST Pool Driver Values',
    'CST Pool to Activity Driver Pct',
    'CST Activity to Activity Apportionment',
    'CST Activity to Activity Driver Pct',
    'CST Activity to Activity Driver Values',
    'CST Activity Driver Config',
    'CST Activity Driver Values',
    'CST Activity Driver Input',
    'CST Activity to Service Line Driver Pct',
    'CST Activity to Service Line Apportionment',
    # Legacy — older designs
    'CST GL Input',
    'CST Apportionment Config',
    'CST Cost Pool Apportionment',
    'CST Pool to Pool Driver',
    'CST Pool to Pool Driver Input',
    'CST Activity Apportionment',
    'CST Pool Driver',
    'CST Activity to Activity Driver',
    'CST Activity to Activity Driver Input',
    'CST Service Line Cost',
    'CST Activity Driver',
    'CST Driver Values',
    'CST Account Driver',
    'CST Driver Assumptions',
    'CST Activity Driver Assumptions',
]

DIMENSIONS_TO_DELETE = [
    # Structural dims
    'CST Apportionment Stage',
    'CST Cost Pool',
    'CST Cost Pool Dest',
    'CST Activity',
    'CST Activity Dest',
    'CST Service Line',
    'CST Reconciliation Check',
    'CST Driver',
    # Current measure dims — 10-cube design
    'CST Account Config Measure',
    'CST Account to Pool Apportionment Measure',
    'CST Pool to Pool Config Measure',
    'CST Pool Config Measure',
    'CST Pool to Activity Apportionment Measure',
    'CST Activity to Activity Config Measure',
    'CST Activity Config Measure',
    'CST Activity to Service Line Apportionment Measure',
    'CST Profit and Loss Report Measure',
    'CST Apportionment Reconciliation Measure',
    # Legacy measure dims — 22-cube design
    'CST Account Input Measure',
    'CST Account Driver Config Measure',
    'CST Account Flag Measure',
    'CST Account to Pool Driver Pct Measure',
    'CST Pool to Pool Apportionment Measure',
    'CST Pool to Pool Driver Pct Measure',
    'CST Pool to Pool Driver Values Measure',
    'CST Pool Driver Config Measure',
    'CST Pool Driver Values Measure',
    'CST Pool to Activity Driver Pct Measure',
    'CST Activity to Activity Apportionment Measure',
    'CST Activity to Activity Driver Pct Measure',
    'CST Activity to Activity Driver Values Measure',
    'CST Activity Driver Config Measure',
    'CST Activity Driver Values Measure',
    'CST Activity Driver Input Measure',
    'CST Activity to Service Line Driver Pct Measure',
    'CST Activity to Service Line Apportionment Measure',
    # Legacy measure dims — older designs
    'CST GL Input Measure',
    'CST Pool Driver Measure',
    'CST Pool to Pool Driver Measure',
    'CST Activity Driver Measure',
    'CST Activity to Activity Driver Measure',
    'CST Cost Pool Apportionment Measure',
    'CST Activity Apportionment Measure',
    'CST Service Line Cost Measure',
    'CST Apportionment Config Measure',
    'CST Driver Values Measure',
    'CST Account Driver Measure',
    'CST Pool to Pool Driver Input Measure',
    'CST Activity to Activity Driver Input Measure',
    'CST Driver Assumptions Measure',
    'CST Account Config Measure',
    'CST Activity Driver Assumptions Measure',
    'CST Config Item',
]

print(f"\n{'═'*60}")
print("  Cleanup — CST Module")
print(f"{'═'*60}")

print(f"\n{'─'*60}")
print("  Deleting cubes...")
print(f"{'─'*60}")

# Query server for any CST cubes not in the static list (e.g. from partial builds)
try:
    all_cubes = tm1.cubes.get_all_names()
    extra_cst_cubes = [c for c in all_cubes if c.startswith('CST ') and c not in CUBES_TO_DELETE]
    if extra_cst_cubes:
        print(f"  ! Found {len(extra_cst_cubes)} additional CST cube(s) on server — will delete:")
        for c in extra_cst_cubes:
            print(f"      {c}")
        CUBES_TO_DELETE.extend(extra_cst_cubes)
except Exception:
    pass

cubes_deleted = 0
cube_errors   = 0
for name in CUBES_TO_DELETE:
    try:
        if tm1.cubes.exists(name):
            tm1.cubes.delete(name)
            print(f"  ✓ {name}")
            cubes_deleted += 1
        else:
            print(f"  - (not found) {name}")
    except Exception as e:
        print(f"  ✗ {name} — {e}")
        cube_errors += 1

print(f"\n{'─'*60}")
print("  Deleting dimensions...")
print(f"{'─'*60}")
dims_deleted = 0
dims_errors  = 0
for name in DIMENSIONS_TO_DELETE:
    try:
        if tm1.dimensions.exists(name):
            tm1.dimensions.delete(name)
            print(f"  ✓ {name}")
            dims_deleted += 1
        else:
            print(f"  - (not found) {name}")
    except Exception as e:
        print(f"  ✗ {name} — {e}")
        dims_errors += 1

try:
    tm1.logout()
except Exception:
    pass

print(f"\n{'═'*60}")
print(f"  CST cleanup complete.")
print(f"  Cubes deleted     : {cubes_deleted} of {len(CUBES_TO_DELETE)}")
print(f"  Dimensions deleted: {dims_deleted} of {len(DIMENSIONS_TO_DELETE)}")
if cube_errors or dims_errors:
    print(f"  ✗ Errors          : {cube_errors} cube(s), {dims_errors} dimension(s) failed to delete")
print(f"  GBL untouched (except Input sentinel in GBL Cost Centre).")
print(f"  Ready to run build_cst_model.py.")
print(f"{'═'*60}")
sys.exit(0)
