import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

OUT = Path(__file__).parent / 'tm1_objects' / 'views'

with get_tm1_service() as tm1:
    for cube_name in tm1.cubes.get_all_names():
        if cube_name.startswith('}'):
            continue
        _, names = tm1.views.get_all_names(cube_name, private=False)
        if not names:
            continue
        cube_dir = OUT / cube_name
        cube_dir.mkdir(parents=True, exist_ok=True)
        for name in names:
            view = tm1.views.get(cube_name, name, private=False)
            out_file = cube_dir / f"{name}.json"
            out_file.write_text(json.dumps(view.body, indent=2))
            print(f"  {cube_name} / {name}")

