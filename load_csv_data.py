"""
Load sample CSV data directly into TM1 cubes via REST API.
Skips TI processes — writes data directly through TM1py.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "model_builder"))
from deployment_config import TM1_CONFIG
import config

config.TM1_CONFIG = TM1_CONFIG
from tm1py_connect import get_tm1_service

BASE = Path(__file__).parent / "sample_data"

# Each entry: (csv_file, cube_name, [dim_names...], value_col, {col_map}, {defaults})
# col_map: csv_header -> tm1_dim_name   (if different)
# defaults: dim_name -> default_value   (for missing dimensions)
CSV_JOBS = [
    ("Load_GL_Account.csv", "CST Account Config", None, "vAmount", {}, {}),
    ("Load_Apportionment_Type.csv", "CST Account Config", None, "vAmount", {}, {}),
    ("Load_Direct_Account_SL_pct.csv", "CST Account Config", None, "vAmount", {}, {}),
    ("Load_Account_Pool_pct.csv", "CST Account Config", None, "vAmount", {}, {}),
    (
        "Load_Cost_Pool_to_Activity_Driver_Value.csv",
        "CST Pool Config",
        [
            "GBL Period",
            "GBL Version",
            "CST Cost Pool",
            "CST Driver",
            "CST Activity",
            "CST Pool Config Measure",
        ],
        "Value",
        {
            "Period": "GBL Period",
            "Version": "GBL Version",
            "Cost Pool": "CST Cost Pool",
            "Driver": "CST Driver",
            "Activity": "CST Activity",
            "Measure": "CST Pool Config Measure",
        },
        {},
    ),
    (
        "Load_Pool_to_Pool_Drivers.csv",
        "CST Pool to Pool Config",
        [
            "GBL Period",
            "GBL Version",
            "CST Cost Pool",
            "CST Cost Pool Dest",
            "GBL Cost Centre",
            "CST Pool to Pool Config Measure",
        ],
        "vAmount",
        {},
        {"GBL Cost Centre": "Input"},
    ),
    (
        "Load_Activity_to_Activity_Drivers.csv",
        "CST Activity to Activity Config",
        [
            "GBL Period",
            "GBL Version",
            "CST Activity",
            "CST Activity Dest",
            "GBL Cost Centre",
            "CST Activity to Activity Config Measure",
        ],
        "vAmount",
        {"vGBP Period": "GBL Period"},
        {"GBL Cost Centre": "Input"},
    ),
    (
        "Load_Activity_to_Service_Line_Driver_Value.csv",
        "CST Activity Config",
        [
            "GBL Period",
            "GBL Version",
            "CST Activity",
            "CST Driver",
            "CST Service Line",
            "CST Activity Config Measure",
        ],
        "vAmount",
        {},
        {},
    ),
]


def load_csv(tm1, csv_path: str, cube: str, dims, val_col, col_map, defaults):
    print(f"  Loading {Path(csv_path).name} -> {cube} ...", end=" ")
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("SKIP (empty)")
        return

    # Build value column name from CSV headers
    if val_col not in rows[0]:
        # Try to find the right column
        candidates = [c for c in rows[0] if c.lower() in ("value", "vamount")]
        if candidates:
            val_col = candidates[0]
        else:
            print(f"FAIL: value column not found in {list(rows[0].keys())}")
            return

    # If dims is None, derive from CSV headers (default path)
    if dims is None:
        headers = [c for c in rows[0] if c != val_col]
        dims = [h[1:] if h.startswith("v") else h for h in headers]
        col_map = dict(zip(headers, dims))

    # Write in chunks to avoid huge payloads
    chunk_size = 2000
    total = 0
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        cells = {}
        for row in chunk:
            key = []
            for d in dims:
                # Check defaults first
                if d in defaults:
                    key.append(defaults[d])
                else:
                    # Find CSV column that maps to this dim
                    csv_col = None
                    for csv_h, tm1_d in col_map.items():
                        if tm1_d == d:
                            csv_col = csv_h
                            break
                    if csv_col is None:
                        csv_col = d
                        # Try with v prefix
                        v_key = f"v{d}"
                        if v_key in row:
                            csv_col = v_key
                    key.append(row[csv_col])
            val = row[val_col]
            if val and val.strip():
                try:
                    cells[tuple(key)] = float(val)
                except ValueError:
                    cells[tuple(key)] = val
        if cells:
            tm1.cells.write_values(cube, cells, dimensions=dims)
            total += len(cells)
    print(f"{total} cells")


def main():
    with get_tm1_service() as tm1:
        print("Connected to TM1_Apportionment")
        for csv_name, cube, dims, val_col, col_map, defaults in CSV_JOBS:
            csv_path = BASE / csv_name
            if not csv_path.exists():
                print(f"  SKIP {csv_name} (not found)")
                continue
            load_csv(tm1, csv_path, cube, dims, val_col, col_map, defaults)
    print("\nDone")


if __name__ == "__main__":
    main()
