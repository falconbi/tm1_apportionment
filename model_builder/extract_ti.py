import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

OUT = Path(__file__).parent / 'tm1_objects' / 'processes'
OUT.mkdir(parents=True, exist_ok=True)

with get_tm1_service() as tm1:
    for name in tm1.processes.get_all_names():
        if name.startswith('}'):
            continue
        process = tm1.processes.get(name)
        out_file = OUT / f"{name}.json"
        out_file.write_text(json.dumps(process.body_as_dict, indent=2))
        print(f"  {name}")

