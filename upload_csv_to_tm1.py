"""
Upload sample CSV files to the TM1 server's data directory via REST API.
After running this, the TI processes can find the files for CSV import.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "model_builder"))
from deployment_config import TM1_CONFIG
import config

config.TM1_CONFIG = TM1_CONFIG
from tm1py_connect import get_tm1_service

BASE = Path(__file__).parent / "sample_data"

CSV_FILES = [
    "Load_GL_Account.csv",
    "Load_Apportionment_Type.csv",
    "Load_Direct_Account_SL_pct.csv",
    "Load_Account_Pool_pct.csv",
    "Load_Cost_Pool_to_Activity_Driver_Value.csv",
    "Load_Pool_to_Pool_Drivers.csv",
    "Load_Activity_to_Activity_Drivers.csv",
    "Load_Activity_to_Service_Line_Driver_Value.csv",
]


def main():
    with get_tm1_service() as tm1:
        print("Uploading CSV files to TM1 data directory...")
        for name in CSV_FILES:
            path = BASE / name
            if not path.exists():
                print(f"  SKIP {name} (not found)")
                continue
            content = path.read_bytes()
            tm1.files.update_or_create(name, content)
            print(f"  Uploaded {name}")
    print("Done")


if __name__ == "__main__":
    main()
