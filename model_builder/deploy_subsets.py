"""
deploy_subsets.py
Reads subset definitions from subsets/*.yaml and deploys them to TM1.
Each YAML file defines one dimension with one or more named subsets.
Safe to re-run — deletes existing subsets before recreating them.

Usage:
    python3 model_builder/deploy_subsets.py                        # all files
    python3 model_builder/deploy_subsets.py cst_cost_pool          # one dim by filename stem
    python3 model_builder/deploy_subsets.py cst_cost_pool cst_activity  # multiple
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, '.')
from TM1py.Objects import Subset
from tm1py_connect import get_tm1_service

SUBSETS_DIR = Path(__file__).resolve().parent.parent / 'subsets'


def _make_subset(subset_name, dim_name, s):
    if 'mdx' in s:
        return Subset(
            subset_name=subset_name,
            dimension_name=dim_name,
            hierarchy_name=dim_name,
            expression=s['mdx'],
        )
    return Subset(
        subset_name=subset_name,
        dimension_name=dim_name,
        hierarchy_name=dim_name,
        elements=s['elements'],
    )


def _set_default_subset(tm1, dim_name, s):
    """Create/replace a subset named 'Default' — TM1 opens this automatically."""
    if tm1.subsets.exists('Default', dim_name, private=False):
        tm1.subsets.delete('Default', dim_name, private=False)
    tm1.subsets.create(_make_subset('Default', dim_name, s), private=False)


def deploy_file(tm1, path, deployed, skipped):
    defn = yaml.safe_load(path.read_text())
    dim_name = defn['dimension']

    if not tm1.dimensions.exists(dim_name):
        print(f"  - {dim_name} — dimension not found, skipping")
        skipped += 1
        return deployed, skipped

    for s in defn['subsets']:
        subset_name = s['subset_name']
        if tm1.subsets.exists(subset_name, dim_name, private=False):
            tm1.subsets.delete(subset_name, dim_name, private=False)

        tm1.subsets.create(_make_subset(subset_name, dim_name, s), private=False)

        if s.get('set_as_default', False):
            _set_default_subset(tm1, dim_name, s)
            print(f"  ✓ {dim_name} — {subset_name} + Default")
        else:
            print(f"  ✓ {dim_name} — {subset_name}")
        deployed += 1

    return deployed, skipped


def main(tm1, targets=None):
    print(f"\n{'─'*60}")
    print("  Deploying CST subsets...")
    print(f"{'─'*60}")

    if targets:
        subset_files = []
        for t in targets:
            p = SUBSETS_DIR / (t if t.endswith('.yaml') else f"{t}.yaml")
            if not p.exists():
                print(f"  ! {p.name} not found")
            else:
                subset_files.append(p)
    else:
        subset_files = sorted(SUBSETS_DIR.glob('*.yaml'))

    if not subset_files:
        print(f"  ! No subset definition files found")
        return 0

    deployed = skipped = 0
    for path in subset_files:
        deployed, skipped = deploy_file(tm1, path, deployed, skipped)

    print(f"{'─'*60}")
    print(f"  {deployed} subsets deployed" + (f", {skipped} skipped" if skipped else ""))
    print(f"{'─'*60}\n")
    return deployed


if __name__ == '__main__':
    targets = sys.argv[1:] or None
    with get_tm1_service() as tm1:
        main(tm1, targets)
