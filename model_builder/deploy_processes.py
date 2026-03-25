"""
deploy_processes.py
Reads process definitions from processes/*.yaml and deploys them to TM1
as native TurboIntegrator processes.
Safe to re-run — deletes existing process before recreating.

Usage:
    python3 model_builder/deploy_processes.py                        # all files
    python3 model_builder/deploy_processes.py cst_load_drivers       # one process by filename stem
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, '.')
from TM1py.Objects import Process
from tm1py_connect import get_tm1_service

PROCESSES_DIR = Path(__file__).resolve().parent.parent / 'ti_processes'


def deploy_file(tm1, path):
    defn = yaml.safe_load(path.read_text())

    ds = defn.get('datasource', {})
    process = Process(
        name                              = defn['name'],
        datasource_type                   = ds.get('type', 'None'),
        datasource_data_source_name_for_server = ds.get('cube', ''),
        datasource_data_source_name_for_client = ds.get('cube', ''),
        datasource_view                   = ds.get('view', ''),
        prolog_procedure                  = defn.get('prolog', ''),
        metadata_procedure                = defn.get('metadata', ''),
        data_procedure                    = defn.get('data', ''),
        epilog_procedure                  = defn.get('epilog', ''),
    )

    for param in defn.get('parameters', []):
        process.add_parameter(
            name           = param['name'],
            prompt         = param['prompt'],
            value          = param['default'],
            parameter_type = param['type'],
        )

    for var in defn.get('variables', []):
        process.add_variable(
            name          = var['name'],
            variable_type = var['type'],
        )

    if tm1.processes.exists(defn['name']):
        tm1.processes.delete(defn['name'])
    tm1.processes.create(process)
    print(f"  ✓ {defn['name']}")


def main(tm1, targets=None):
    print(f"\n{'─'*60}")
    print("  Deploying CST processes...")
    print(f"{'─'*60}")

    if targets:
        process_files = []
        for t in targets:
            p = PROCESSES_DIR / (t if t.endswith('.yaml') else f"{t}.yaml")
            if not p.exists():
                print(f"  ! {p.name} not found")
            else:
                process_files.append(p)
    else:
        process_files = sorted(PROCESSES_DIR.glob('*.yaml'))

    if not process_files:
        print("  ! No process definition files found")
        return 0

    deployed = 0
    for path in process_files:
        deploy_file(tm1, path)
        deployed += 1

    print(f"{'─'*60}")
    print(f"  {deployed} processes deployed")
    print(f"{'─'*60}\n")
    return deployed


if __name__ == '__main__':
    targets = sys.argv[1:] or None
    with get_tm1_service() as tm1:
        main(tm1, targets)
