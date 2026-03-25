"""
generate_model_store.py
Writes all CST and GBL TM1 metadata into a SQLite database.

Tables:
  cubes       — cube_name, dimension_names (pipe-separated, in order)
  dimensions  — dimension_name, element_name, element_type, parent_name, weight
  attributes  — dimension_name, element_name, attribute_name, attribute_type, attribute_value

Run standalone:
    python3 model_builder/generate_model_store.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service

DB_PATH = Path(__file__).resolve().parent.parent / 'tests' / 'data' / 'cst_model_store.db'

DDL = """
CREATE TABLE cubes (
    cube_name        TEXT PRIMARY KEY,
    dimension_names  TEXT NOT NULL   -- pipe-separated, in dimension order
);
CREATE TABLE dimensions (
    dimension_name  TEXT NOT NULL,
    element_name    TEXT NOT NULL,
    element_type    TEXT NOT NULL,
    parent_name     TEXT,
    weight          REAL,
    PRIMARY KEY (dimension_name, element_name, parent_name)
);
CREATE TABLE attributes (
    dimension_name   TEXT NOT NULL,
    element_name     TEXT NOT NULL,
    attribute_name   TEXT NOT NULL,
    attribute_type   TEXT NOT NULL,
    attribute_value  TEXT,
    PRIMARY KEY (dimension_name, element_name, attribute_name)
);
"""


def _attr_values(tm1, dim_name, attr_names, element_names):
    if not attr_names or not element_names:
        return {}
    attr_dim = f'}}ElementAttributes_{dim_name}'
    rows = '{' + ', '.join(f'[{dim_name}].[{dim_name}].[{e}]' for e in element_names) + '}'
    cols = '{' + ', '.join(f'[{attr_dim}].[{attr_dim}].[{a}]' for a in attr_names) + '}'
    mdx  = f'SELECT {cols} ON COLUMNS, {rows} ON ROWS FROM [{attr_dim}]'
    try:
        return {coords: str(cell.get('Value') or '')
                for coords, cell in tm1.cells.execute_mdx(mdx).items()}
    except Exception:
        return {}


def main(tm1=None):
    own = tm1 is None
    if own:
        tm1 = get_tm1_service()

    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        if DB_PATH.exists():
            DB_PATH.unlink()

        conn = sqlite3.connect(DB_PATH)
        conn.executescript(DDL)

        all_cubes = tm1.cubes.get_all_names()
        all_dims  = tm1.dimensions.get_all_names()

        target_cubes = [c for c in all_cubes if c.startswith('CST ') or c.startswith('GBL ')]
        target_dims  = [d for d in all_dims  if d.startswith('CST ') or d.startswith('GBL ')]

        # cubes
        cube_rows = []
        for name in target_cubes:
            cube = tm1.cubes.get(name)
            cube_rows.append((name, '|'.join(cube.dimensions)))
        conn.executemany('INSERT INTO cubes VALUES (?,?)', cube_rows)

        # dimensions + attributes
        dim_rows  = []
        attr_rows = []

        for dim_name in target_dims:
            dim  = tm1.dimensions.get(dim_name)
            hier = dim.default_hierarchy

            # child -> [(parent, weight)]
            child_parents = {}
            for (parent, child), weight in hier.edges.items():
                child_parents.setdefault(child, []).append((parent, weight))

            el_names = list(hier.elements.keys())
            for el_name, el in hier.elements.items():
                el_type = el.element_type.name.capitalize()
                parents = child_parents.get(el_name)
                if parents:
                    for parent, weight in parents:
                        dim_rows.append((dim_name, el_name, el_type, parent, weight))
                else:
                    dim_rows.append((dim_name, el_name, el_type, None, None))

            try:
                attrs = tm1.elements.get_element_attributes(dim_name, dim_name)
            except Exception:
                attrs = []

            if attrs:
                attr_names = [a.name for a in attrs]
                vals = _attr_values(tm1, dim_name, attr_names, el_names)
                for el_name in el_names:
                    for a in attrs:
                        v = vals.get((el_name, a.name), vals.get((a.name, el_name), ''))
                        attr_rows.append((dim_name, el_name, a.name, a.attribute_type, v))

        conn.executemany('INSERT INTO dimensions VALUES (?,?,?,?,?)', dim_rows)
        conn.executemany('INSERT INTO attributes VALUES (?,?,?,?,?)', attr_rows)
        conn.commit()

        counts = {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                  for t in ('cubes', 'dimensions', 'attributes')}
        conn.close()

        print(f"  ✓ Model store: {DB_PATH}")
        for t, n in counts.items():
            print(f"      {t:<14} {n:>4} rows")

    finally:
        if own:
            tm1.logout()


if __name__ == '__main__':
    main()
