"""
create_gbl_account.py
Builds the GBL Account dimension using TM1py.

Element names: account codes (4001, 6003 etc)
Aliases:       Code & Desc (e.g. '6003 Building Depreciation')
               Desc        (e.g. 'Building Depreciation')

Hierarchy: Net Profit at top, revenue/costs/overhead/allocated overhead below.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service
from TM1py.Objects import Dimension, Hierarchy

DIM = 'GBL Account'

# ── Account data ──────────────────────────────────────────────────────────────
# (code, desc, el_type, parent, weight)
ACCOUNTS = [
    # Consolidations
    ('NET PROFIT',         'Net Profit',         'Consolidated', None,                  1),
    ('TOTAL REVENUE',      'Total Revenue',       'Consolidated', 'NET PROFIT',          1),
    ('TOTAL DIRECT COSTS', 'Total Direct Costs',  'Consolidated', 'NET PROFIT',         -1),
    ('TOTAL OVERHEAD',     'Total Overhead',       'Consolidated', 'NET PROFIT',         -1),
    ('ALLOCATED OVERHEAD', 'Allocated Overhead',   'Consolidated', 'NET PROFIT',         -1),
    # Revenue 4000s
    ('4001', 'Inpatient Revenue',               'Numeric', 'TOTAL REVENUE',       1),
    ('4002', 'Outpatient Revenue',              'Numeric', 'TOTAL REVENUE',       1),
    ('4003', 'Radiology Revenue',               'Numeric', 'TOTAL REVENUE',       1),
    ('4004', 'Pathology Revenue',               'Numeric', 'TOTAL REVENUE',       1),
    ('4005', 'Other Revenue',                   'Numeric', 'TOTAL REVENUE',       1),
    # Direct Costs 5000s
    ('5001', 'Direct Labour',                   'Numeric', 'TOTAL DIRECT COSTS',  1),
    ('5002', 'Direct Materials',                'Numeric', 'TOTAL DIRECT COSTS',  1),
    ('5003', 'Direct Supplies',                 'Numeric', 'TOTAL DIRECT COSTS',  1),
    # Overhead 6000s
    ('6001', 'Indirect Nursing Salaries',       'Numeric', 'TOTAL OVERHEAD',      1),
    ('6002', 'Medical Administration Salaries', 'Numeric', 'TOTAL OVERHEAD',      1),
    ('6003', 'Building Depreciation',           'Numeric', 'TOTAL OVERHEAD',      1),
    ('6004', 'Rent and Rates',                  'Numeric', 'TOTAL OVERHEAD',      1),
    ('6005', 'Cleaning and Waste',              'Numeric', 'TOTAL OVERHEAD',      1),
    ('6006', 'Medical Equipment Depreciation',  'Numeric', 'TOTAL OVERHEAD',      1),
    ('6007', 'Equipment Maintenance',           'Numeric', 'TOTAL OVERHEAD',      1),
    ('6008', 'IT Infrastructure',               'Numeric', 'TOTAL OVERHEAD',      1),
    ('6009', 'Software Licences',               'Numeric', 'TOTAL OVERHEAD',      1),
    ('6010', 'IT Helpdesk',                     'Numeric', 'TOTAL OVERHEAD',      1),
    ('6011', 'Recruitment Costs',               'Numeric', 'TOTAL OVERHEAD',      1),
    ('6012', 'Training and Development',        'Numeric', 'TOTAL OVERHEAD',      1),
    ('6013', 'HR Administration',               'Numeric', 'TOTAL OVERHEAD',      1),
    ('6014', 'Finance Team Salaries',           'Numeric', 'TOTAL OVERHEAD',      1),
    ('6015', 'Payroll Processing',              'Numeric', 'TOTAL OVERHEAD',      1),
    ('6016', 'Accounts Payable',                'Numeric', 'TOTAL OVERHEAD',      1),
    ('6017', 'Autoclave Operation',             'Numeric', 'TOTAL OVERHEAD',      1),
    ('6018', 'Sterilisation Materials',         'Numeric', 'TOTAL OVERHEAD',      1),
    ('6019', 'Orderly Salaries',                'Numeric', 'TOTAL OVERHEAD',      1),
    ('6020', 'Patient Transfer Equipment',      'Numeric', 'TOTAL OVERHEAD',      1),
    ('6021', 'Catering Salaries',               'Numeric', 'TOTAL OVERHEAD',      1),
    ('6022', 'Food and Beverage',               'Numeric', 'TOTAL OVERHEAD',      1),
    ('6023', 'Executive Salaries',              'Numeric', 'TOTAL OVERHEAD',      1),
    ('6024', 'Board Costs',                     'Numeric', 'TOTAL OVERHEAD',      1),
    ('6025', 'Legal and Compliance',            'Numeric', 'TOTAL OVERHEAD',      1),
    ('6026', 'Accreditation Costs',             'Numeric', 'TOTAL OVERHEAD',      1),
    # Allocated Overhead 7000s
    ('7000', 'Allocated Overhead',              'Numeric', 'ALLOCATED OVERHEAD',  1),
]


def main(tm1):
    print(f"\n  Building {DIM}...")

    h = Hierarchy(name=DIM, dimension_name=DIM)
    h.add_element_attribute('Code & Desc', 'Alias')
    h.add_element_attribute('Desc', 'Alias')

    for code, desc, el_type, parent, weight in ACCOUNTS:
        h.add_element(code, el_type)
        if parent:
            h.add_edge(parent, code, weight)

    d = Dimension(name=DIM, hierarchies=[h])
    tm1.dimensions.update_or_create(d)

    cube_name = f"}}ElementAttributes_{DIM}"
    dims      = [DIM, f"}}ElementAttributes_{DIM}"]
    cells     = {}
    for code, desc, el_type, parent, weight in ACCOUNTS:
        if el_type == 'Numeric':
            cells[(code, 'Code & Desc')] = f"{code} {desc}"
            cells[(code, 'Desc')]        = desc
        else:
            cells[(code, 'Code & Desc')] = desc
            cells[(code, 'Desc')]        = desc

    tm1.cells.write_values(cube_name, cells, dimensions=dims)

    leaf_count = sum(1 for _, _, t, _, _ in ACCOUNTS if t == 'Numeric')
    print(f"  ✓ {DIM} — {leaf_count} accounts")


if __name__ == '__main__':
    with get_tm1_service() as tm1:
        main(tm1)
