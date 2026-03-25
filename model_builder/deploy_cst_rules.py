"""
deploy_cst_rules.py
Reads rule definitions from rules/*.yaml and deploys them to TM1.
Safe to re-run — uses update_or_create_rules.

Usage:
    python3 model_builder/deploy_cst_rules.py                          # all files
    python3 model_builder/deploy_cst_rules.py cst_activity_apportionment
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, '.')
from tm1py_connect import get_tm1_service

RULES_DIR = Path(__file__).resolve().parent.parent / 'rules'


def deploy_file(tm1, path):
    defn = yaml.safe_load(path.read_text())
    cube_name = defn['cube']
    rule_text = defn['rule']

    if not tm1.cubes.exists(cube_name):
        print(f"  ! {cube_name} — cube not found, skipping")
        return False

    tm1.cubes.update_or_create_rules(cube_name, rule_text)
    print(f"  ✓ {cube_name}")
    return True


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

    deployed = 0
    for path in rule_files:
        if deploy_file(tm1, path):
            deployed += 1

    print(f"{'─'*60}")
    print(f"  {deployed} rules deployed")
    print(f"{'─'*60}\n")
    return deployed


if __name__ == '__main__':
    targets = sys.argv[1:] or None
    with get_tm1_service() as tm1:
        main(tm1, targets)
