import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

OUT = Path(__file__).parent / "tm1_objects" / "subsets"

with get_tm1_service() as tm1:
    for dim in tm1.dimensions.get_all_names():
        names = tm1.subsets.get_all_names(dim, private=False)
        if not names:
            continue
        dim_dir = OUT / dim
        dim_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            subset = tm1.subsets.get(name, dim, private=False)
            out_file = dim_dir / f"{name}.json"
            out_file.write_text(json.dumps(subset.body_as_dict, indent=2))
            print(f"  {dim} / {name}")
