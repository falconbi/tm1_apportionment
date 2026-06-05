import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

OUT = Path(__file__).parent / "tm1_objects" / "dimensions"
OUT.mkdir(parents=True, exist_ok=True)

with get_tm1_service() as tm1:
    for dim_name in tm1.dimensions.get_all_names():
        # Skip system dimensions
        if dim_name.startswith("}"):
            continue

        hierarchy = tm1.hierarchies.get(dim_name, dim_name)
        attributes = tm1.elements.get_element_attributes(dim_name, dim_name)

        # Attribute values — read attribute cube in one MDX call
        attr_values = {}
        if attributes:
            attr_cube = f"}}ElementAttributes_{dim_name}"
            try:
                mdx = (
                    f"SELECT {{TM1SUBSETALL([{dim_name}])}} ON 0, "
                    f"{{TM1SUBSETALL([{attr_cube}])}} ON 1 "
                    f"FROM [{attr_cube}]"
                )
                raw = tm1.cells.execute_mdx(
                    mdx, skip_zeros=False, element_unique_names=False
                )
                for key, cell in raw.items():
                    elem, attr = key[0], key[1]
                    attr_values.setdefault(elem, {})[attr] = cell.get("Value", "")
            except Exception as e:
                print(f"  Attribute cube not found for {dim_name}: {e}")
                attr_values = {}

        output = {
            "name": dim_name,
            "elements": [
                {"name": e.name, "type": str(e.element_type)}
                for e in hierarchy.elements.values()
            ],
            "edges": [
                {"parent": str(parent), "component": str(comp), "weight": float(weight)}
                for (parent, comp), weight in hierarchy.edges.items()
            ],
            "attributes": [
                {"name": a.name, "type": str(a.attribute_type)} for a in attributes
            ],
            "attribute_values": attr_values,
        }

        out_file = OUT / f"{dim_name}.json"
        out_file.write_text(json.dumps(output, indent=2))
        print(
            f"  {dim_name}  ({len(hierarchy.elements)} elements, {len(attributes)} attributes)"
        )
