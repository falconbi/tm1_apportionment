"""
build_cst_model.py
Orchestrator — builds the full CST apportionment module on TM1.

Run order:
  python3 model_builder/build_cst_model.py

Prerequisites:
  GBL dimensions must already exist (built via tm1_global).
  Run cleanup_cst_model.py first for a clean rebuild.
"""

import sys
sys.path.insert(0, '.')
from tm1py_connect import get_tm1_service
from gbl_check import verify_gbl

import create_cst_dimensions
import create_cst_apportionment_stage
import create_cst_cubes
import deploy_cst_rules
import deploy_views
import deploy_processes
import generate_model_store

print(f"\n{'═'*60}")
print("  Build — CST Apportionment Module")
print(f"{'═'*60}")

tm1 = get_tm1_service()

print(f"\n{'─'*60}")
print("  Checking GBL prerequisites...")
print(f"{'─'*60}")
verify_gbl(tm1)

# Step 1 — CST dimensions (cost pools, activities, service lines, measures, etc.)
create_cst_dimensions.main(tm1)

# Step 2 — CST Apportionment Stage dimension
print(f"\n{'─'*60}")
print("  Creating CST Apportionment Stage...")
print(f"{'─'*60}")
create_cst_apportionment_stage.main(tm1)

# Step 3 — All CST cubes
create_cst_cubes.main(tm1)

# Step 5 — Rules (must follow cube creation — rules are deleted with the cube)
deploy_cst_rules.main(tm1)

# Step 6 — TI processes
deploy_processes.main(tm1)

# Step 7 — Default views for all cubes
deploy_views.main(tm1)

# Step 8 — Write model store
generate_model_store.main(tm1)

tm1.logout()

print(f"\n{'═'*60}")
print("  CST Apportionment Module — build complete.")
print(f"  Dimensions : CST Cost Pool, CST Cost Pool Dest,")
print(f"               CST Activity, CST Activity Dest,")
print(f"               CST Service Line, CST Reconciliation Check,")
print(f"               CST Driver, CST Apportionment Stage,")
print(f"               + measure dimensions")
print(f"  Cubes      : 10 CST cubes")
print(f"{'═'*60}")
