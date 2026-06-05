import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

OUT = Path(__file__).parent / 'tm1_objects' / 'cubes'
OUT.mkdir(parents=True, exist_ok=True)

with get_tm1_service() as tm1:
    for cube_name in tm1.cubes.get_all_names():
        if cube_name.startswith('}'):
            continue
        try:
            cube = tm1.cubes.get(cube_name)
            output = {
                'name': cube.name,
                'dimensions': cube.dimensions,
                'rules': cube.rules.text if cube.rules else '',
                'measures': []
            }
            # Get measure names from the measure dimension if it exists
            for dim in cube.dimensions:
                if 'Measure' in dim:
                    try:
                        measures = tm1.elements.get_all_elements(dim, dim)
                        output['measures'] = [m for m in measures.keys()]
                    except:
                        pass
            out_file = OUT / f"{cube_name}.json"
            out_file.write_text(json.dumps(output, indent=2))
            print(f"  {cube_name}")
        except Exception as e:
            print(f"  Error {cube_name}: {e}")
