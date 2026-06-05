"""
model_builder/deploy.py
Deploys full TM1 model from extracted JSON files to target server.

Deploy order:
  1. Dimensions  — elements, consolidations, attributes, attribute values
  2. Cubes       — dimension list + rules
  3. Subsets     — public subsets per dimension
  4. Views       — public views per cube
  5. Processes   — TI processes
"""

import json
import requests
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from deployment_config import TM1_CONFIG

config.TM1_CONFIG = TM1_CONFIG  # point tm1py_connect at deployment target
from tm1py_connect import get_tm1_service
from TM1py.Objects import Dimension, Hierarchy, Element, ElementAttribute, Cube, Rules
from TM1py.Objects import Subset, MDXView, NativeView, Process

BASE = Path(__file__).parent / "tm1_objects"


def deploy_dimensions(tm1):
    print("\n── Dimensions ──")
    for f in sorted((BASE / "dimensions").glob("*.json")):
        data = json.loads(f.read_text())
        dim_name = data["name"]

        hierarchy = Hierarchy(dim_name, dim_name)
        for e in data["elements"]:
            hierarchy.add_element(e["name"], e["type"])
        for edge in data.get("edges", []):
            hierarchy.add_edge(edge["parent"], edge["component"], edge["weight"])

        dim = Dimension(dim_name, [hierarchy])
        if tm1.dimensions.exists(dim_name):
            tm1.dimensions.update(dim)
        else:
            tm1.dimensions.create(dim)

        # Create attributes first — TM1 auto-creates }ElementAttributes_ cube on first attribute
        for attr in data.get("attributes", []):
            try:
                tm1.elements.create_element_attribute(
                    dim_name, dim_name, ElementAttribute(attr["name"], attr["type"])
                )
            except Exception as e:
                print(f"    ! attribute {attr['name']}: {e}")

        # Write attribute values
        attr_values = data.get("attribute_values", {})
        if attr_values:
            attr_cube = f"}}ElementAttributes_{dim_name}"
            attr_dims = [dim_name, attr_cube]
            cells = {}
            for elem, attrs in attr_values.items():
                for attr, val in attrs.items():
                    if val is not None:
                        cells[(elem, attr)] = val
            if cells:
                tm1.cells.write_values(attr_cube, cells, dimensions=attr_dims)

        print(f"  ✓ {dim_name}")


def deploy_cubes(tm1):
    print("\n── Cubes ──")
    for f in sorted((BASE / "cubes").glob("*.json")):
        data = json.loads(f.read_text())
        cube_name = data["name"]

        cube = Cube(cube_name, data["dimensions"])
        if tm1.cubes.exists(cube_name):
            tm1.cubes.update(cube)
        else:
            tm1.cubes.create(cube)

        if data.get("rules"):
            rules = Rules(data["rules"])
            tm1.cubes.update_or_create_rules(cube_name, rules)

        print(f"  ✓ {cube_name}")


def deploy_subsets(tm1):
    print("\n── Subsets ──")
    for dim_dir in sorted((BASE / "subsets").iterdir()):
        if not dim_dir.is_dir():
            continue
        for f in sorted(dim_dir.glob("*.json")):
            data = json.loads(f.read_text())
            if data.get("Expression"):
                subset = Subset(
                    subset_name=data["Name"],
                    dimension_name=dim_dir.name,
                    hierarchy_name=dim_dir.name,
                    expression=data["Expression"],
                )
            else:
                subset = Subset(
                    subset_name=data["Name"],
                    dimension_name=dim_dir.name,
                    hierarchy_name=dim_dir.name,
                    elements=data.get("Elements", []),
                )
            if tm1.subsets.exists(data["Name"], dim_dir.name, private=False):
                tm1.subsets.update(subset, private=False)
            else:
                tm1.subsets.create(subset, private=False)
            print(f"  ✓ {dim_dir.name} / {data['Name']}")


def deploy_views(tm1):
    print("\n── Views ──")
    for cube_dir in sorted((BASE / "views").iterdir()):
        if not cube_dir.is_dir():
            continue
        for f in sorted(cube_dir.glob("*.json")):
            data = json.loads(f.read_text())
            if isinstance(data, str):
                data = json.loads(data)
            cube_name = cube_dir.name
            if "MDX" in data:
                view = MDXView.from_dict(data, cube_name=cube_name)
            else:
                view = NativeView.from_dict(data, cube_name=cube_name)
            if tm1.views.exists(cube_name, view.name, private=False):
                tm1.views.update(view, private=False)
            else:
                tm1.views.create(view, private=False)
            print(f"  ✓ {cube_name} / {view.name}")


def deploy_processes(tm1):
    print("\n── Processes ──")
    for f in sorted((BASE / "processes").glob("*.json")):
        data = json.loads(f.read_text())
        process = Process.from_dict(data)
        if tm1.processes.exists(process.name):
            tm1.processes.update(process)
        else:
            tm1.processes.create(process)
        print(f"  ✓ {process.name}")


def deploy_files():
    print("\n── CSV Files ──")
    cfg = TM1_CONFIG
    token = __import__("tm1py_connect").get_token()
    url = f"http://192.168.1.223/prism/harmony/tiprocess/api/v1/Servers('{cfg['database']}')/Processes/ImportFile"
    cookies = {"TM1SessionId": token}
    src = Path(__file__).parent.parent / "sample_data"
    for f in sorted(src.glob("*.csv")):
        resp = requests.post(
            url,
            files={"file": (f.name, f.read_bytes(), "text/csv")},
            cookies=cookies,
        )
        if resp.status_code in (200, 201, 204):
            print(f"  ✓ {f.name}")
        else:
            print(f"  ✗ {f.name}: {resp.status_code} {resp.text}")


def main():
    with get_tm1_service() as tm1:
        deploy_dimensions(tm1)
        deploy_cubes(tm1)
        deploy_subsets(tm1)
        deploy_views(tm1)
        deploy_processes(tm1)
    if TM1_CONFIG.get("server_type") != "v11_onprem":
        deploy_files()
    print("\n✓ Deployment complete")


if __name__ == "__main__":
    main()
