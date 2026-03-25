"""
deploy_views.py
Reads view definitions from views/*.yaml and deploys them to TM1.
Each YAML file defines one cube with one or more named views.
Safe to re-run — deletes existing views before recreating them.

Usage:
    python3 model_builder/deploy_views.py                        # all files
    python3 model_builder/deploy_views.py cst_gl_input           # one cube by filename stem
    python3 model_builder/deploy_views.py cst_gl_input cst_pool_driver  # multiple
"""

import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, '.')
from TM1py.Objects import MDXView
from tm1py_connect import get_tm1_service
from config import CST_CONFIG


def _apply_config(text):
    for key, value in CST_CONFIG.items():
        text = text.replace(f'{{{key}}}', value)
    return text

VIEWS_DIR = Path(__file__).resolve().parent.parent / 'views'


def _set_default_view(tm1, cube_name, mdx):
    """Create/replace a view named 'Default' with the same MDX — TM1 opens this automatically."""
    if tm1.views.exists(cube_name, 'Default', private=False):
        tm1.views.delete(cube_name, 'Default', private=False)
    tm1.views.create(MDXView(cube_name, 'Default', mdx), private=False)


def deploy_file(tm1, path, deployed, skipped):
    defn = yaml.safe_load(path.read_text())
    cube_name = defn['cube']

    if not tm1.cubes.exists(cube_name):
        print(f"  - {cube_name} — cube not found, skipping")
        skipped += 1
        return deployed, skipped

    for view in defn['views']:
        view_name = view['view_name']
        mdx       = _apply_config(view['mdx'])
        if tm1.views.exists(cube_name, view_name, private=False):
            tm1.views.delete(cube_name, view_name, private=False)
        tm1.views.create(MDXView(cube_name, view_name, mdx), private=False)
        if view.get('set_as_default', False):
            _set_default_view(tm1, cube_name, mdx)
            print(f"  ✓ {cube_name} — {view_name} + Default")
        else:
            print(f"  ✓ {cube_name} — {view_name}")
        deployed += 1

    return deployed, skipped


def main(tm1, targets=None):
    print(f"\n{'─'*60}")
    print("  Deploying CST views...")
    print(f"{'─'*60}")

    if targets:
        view_files = []
        for t in targets:
            p = VIEWS_DIR / (t if t.endswith('.yaml') else f"{t}.yaml")
            if not p.exists():
                print(f"  ! {p.name} not found")
            else:
                view_files.append(p)
    else:
        view_files = sorted(VIEWS_DIR.glob('*.yaml'))

    if not view_files:
        print(f"  ! No view definition files found")
        return 0

    deployed = skipped = 0
    for path in view_files:
        deployed, skipped = deploy_file(tm1, path, deployed, skipped)

    print(f"{'─'*60}")
    print(f"  {deployed} views deployed" + (f", {skipped} skipped" if skipped else ""))
    print(f"{'─'*60}\n")
    return deployed


if __name__ == '__main__':
    targets = sys.argv[1:] or None
    with get_tm1_service() as tm1:
        main(tm1, targets)
