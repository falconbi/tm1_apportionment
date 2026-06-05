from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

OUT = Path(__file__).parent / "tm1_objects" / "rules"
OUT.mkdir(parents=True, exist_ok=True)

with get_tm1_service() as tm1:
    for cube_name in tm1.cubes.get_all_names():
        try:
            rule = tm1.cubes.get(cube_name).rules
            if rule:
                out_file = OUT / f"{cube_name}.rux"
                out_file.write_text(rule.text)
                print(f"  {cube_name}")
        except Exception as e:
            print(f"  Error {cube_name}: {e}")
