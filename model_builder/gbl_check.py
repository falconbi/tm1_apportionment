"""
gbl_check.py
Verifies required GBL dimensions exist on the TM1 server before
any CST build script runs. Exits with clear message if missing.
"""
import sys

GBL_REQUIRED = [
    'GBL Account',
    'GBL Cost Centre',
    'GBL Period',
    'GBL Version',
]

def verify_gbl(tm1):
    """Call this at the top of every CST build script."""
    missing = [d for d in GBL_REQUIRED if not tm1.dimensions.exists(d)]
    if missing:
        print(f"\n{'═'*60}")
        print(f"  ✗ GBL prerequisite check FAILED")
        print(f"  The following GBL dimensions are missing from TM1:")
        for d in missing:
            print(f"    - {d}")
        print(f"\n  Build tm1_global first:")
        print(f"  cd ~/apps/tm1_global")
        print(f"  python3 model_builder/build_gbl_model.py")
        print(f"{'═'*60}\n")
        sys.exit(1)
    print(f"  ✓ GBL prerequisites — all {len(GBL_REQUIRED)} dimensions present")
