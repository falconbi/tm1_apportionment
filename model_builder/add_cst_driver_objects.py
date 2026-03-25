"""
add_cst_driver_objects.py
SUPERSEDED — driver objects are now created by the main build_cst_model.py.
Kept for reference only.
"""

import sys
sys.path.insert(0, '.')
from tm1py_connect import get_tm1_service
import create_cst_dimensions
import create_cst_cubes
import create_cst_subsets_and_views

NEW_DIMS = [
    'CST Driver',
    'CST Driver Values Measure',
    'CST Account Driver Measure',
    'CST Pool to Pool Driver Input Measure',
    'CST Activity to Activity Driver Input Measure',
    'CST Activity Driver Input Measure',
    'CST Driver Assumptions Measure',
]

NEW_CUBES = [
    'CST Driver Values',
    'CST Account Driver',
    'CST Pool to Pool Driver Input',
    'CST Activity to Activity Driver Input',
    'CST Activity Driver Input',
    'CST Driver Assumptions',
]

print(f"\n{'═'*60}")
print("  Add CST Driver Layer")
print(f"{'═'*60}")

tm1 = get_tm1_service()

# ── Dimensions ───────────────────────────────────────────────
print(f"\n{'─'*60}")
print("  Creating new CST dimensions...")
print(f"{'─'*60}")

create_cst_dimensions.create_cst_driver(tm1)
create_cst_dimensions.create_all_measure_dimensions(tm1)

# ── Cubes ────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("  Creating new CST cubes...")
print(f"{'─'*60}")

from TM1py.Objects import Cube
for cube_name, dimensions in create_cst_cubes.CUBES:
    if cube_name not in NEW_CUBES:
        continue
    missing = [d for d in dimensions if not tm1.dimensions.exists(d)]
    if missing:
        print(f"  ✗ Cannot create '{cube_name}' — missing: {missing}")
        continue
    if tm1.cubes.exists(cube_name):
        tm1.cubes.delete(cube_name)
    cube = Cube(cube_name, dimensions)
    tm1.cubes.create(cube)
    print(f"  ✓ {cube_name}")

# ── Views ────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("  Creating views for new cubes...")
print(f"{'─'*60}")
create_cst_subsets_and_views.create_driver_views(tm1)

try:
    tm1.logout()
except Exception:
    pass

print(f"\n{'═'*60}")
print(f"  Done. {len(NEW_DIMS)} dimensions, {len(NEW_CUBES)} cubes created.")
print(f"{'═'*60}")
