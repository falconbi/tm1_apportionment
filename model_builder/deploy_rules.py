"""
deploy_rules.py
Reads rule definitions from rules/*.yaml and deploys them to TM1.
Each YAML file defines one cube with its rule text.
Safe to re-run — uses update_or_create_rules.

Usage:
    python3 model_builder/deploy_rules.py                        # all files
    python3 model_builder/deploy_rules.py cst_account_config     # one cube by filename stem
    python3 model_builder/deploy_rules.py cst_account_config cst_pool_config  # multiple
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, '.')
from tm1py_connect import get_tm1_service
from config import CST_CONFIG

RULES_DIR = Path(__file__).resolve().parent.parent / 'rules'


def _apply_config(text):
    """Substitute {placeholder} values from CST_CONFIG — uses explicit replace,
    not str.format(), to avoid conflicts with MDX curly braces."""
    for key, value in CST_CONFIG.items():
        text = text.replace(f'{{{key}}}', value)
    return text


def deploy_file(tm1, path, deployed, skipped):
    defn = yaml.safe_load(path.read_text())
    cube_name = defn['cube']

    if not tm1.cubes.exists(cube_name):
        print(f"  - {cube_name} — cube not found, skipping")
        skipped += 1
        return deployed, skipped

    tm1.cubes.update_or_create_rules(cube_name, _apply_config(defn['rule']))
    print(f"  ✓ {cube_name}")
    deployed += 1

    return deployed, skipped


def main(tm1, targets=None):
    print(f"\n{'─'*60}")
    print("  Deploying CST rules...")
    print(f"{'─'*60}")

    if targets:
        rule_files = []
        for t in targets:
            p = RULES_DIR / (t if t.endswith('.yaml') else f"{t}.yaml")
            if not p.exists():
                print(f"  ! {p.name} not found")
            else:
                rule_files.append(p)
    else:
        rule_files = sorted(RULES_DIR.glob('*.yaml'))

    if not rule_files:
        print("  ! No rule definition files found")
        return 0

    deployed = skipped = 0
    for path in rule_files:
        deployed, skipped = deploy_file(tm1, path, deployed, skipped)

    print(f"{'─'*60}")
    print(f"  {deployed} rules deployed" + (f", {skipped} skipped" if skipped else ""))
    print(f"{'─'*60}\n")
    return deployed


if __name__ == '__main__':
    targets = sys.argv[1:] or None
    with get_tm1_service() as tm1:
        main(tm1, targets)
