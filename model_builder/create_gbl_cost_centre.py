"""
create_gbl_cost_centre.py
Builds the GBL Cost Centre dimension using TM1py.

Coding scheme: D001-D017, Code & Desc + Desc aliases
Three-group hierarchy:
  Total Cost Centres
    Total Clinical Cost Centres     (D001-D008)
    Total Administrative Cost Centres (D009-D012)
    Total Support Cost Centres      (D013-D017)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service
from TM1py.Objects import Dimension, Hierarchy

DIM = 'GBL Cost Centre'

STRUCTURE = [
    # Clinical Cost Centres
    ('Total Clinical Cost Centres',         'Total Clinical Cost Centres',         'Consolidated', 'Total Cost Centres'),
    ('D001', 'Emergency Department',         'Numeric',                             'Total Clinical Cost Centres'),
    ('D002', 'Elective Surgery',             'Numeric',                             'Total Clinical Cost Centres'),
    ('D003', 'Intensive Care Unit',          'Numeric',                             'Total Clinical Cost Centres'),
    ('D004', 'Outpatient Clinics',           'Numeric',                             'Total Clinical Cost Centres'),
    ('D005', 'Radiology',                    'Numeric',                             'Total Clinical Cost Centres'),
    ('D006', 'Pathology Laboratory',         'Numeric',                             'Total Clinical Cost Centres'),
    ('D007', 'Maternity',                    'Numeric',                             'Total Clinical Cost Centres'),
    ('D008', 'Allied Health',                'Numeric',                             'Total Clinical Cost Centres'),
    # Administrative Cost Centres
    ('Total Administrative Cost Centres',   'Total Administrative Cost Centres',   'Consolidated', 'Total Cost Centres'),
    ('D009', 'Finance and Administration',   'Numeric',                             'Total Administrative Cost Centres'),
    ('D010', 'Human Resources',              'Numeric',                             'Total Administrative Cost Centres'),
    ('D011', 'Information Technology',       'Numeric',                             'Total Administrative Cost Centres'),
    ('D012', 'Executive and Governance',     'Numeric',                             'Total Administrative Cost Centres'),
    # Support Cost Centres
    ('Total Support Cost Centres',          'Total Support Cost Centres',          'Consolidated', 'Total Cost Centres'),
    ('D013', 'Facility Management',          'Numeric',                             'Total Support Cost Centres'),
    ('D014', 'Clinical Engineering',         'Numeric',                             'Total Support Cost Centres'),
    ('D015', 'Sterilisation Services',       'Numeric',                             'Total Support Cost Centres'),
    ('D016', 'Patient Transport',            'Numeric',                             'Total Support Cost Centres'),
    ('D017', 'Catering Services',            'Numeric',                             'Total Support Cost Centres'),
]


def main(tm1):
    print(f"\n  Building {DIM}...")

    h = Hierarchy(name=DIM, dimension_name=DIM)
    h.add_element_attribute('Code & Desc', 'Alias')
    h.add_element_attribute('Desc',        'Alias')

    h.add_element('Total Cost Centres', 'Consolidated')

    for code, desc, el_type, parent in STRUCTURE:
        h.add_element(code, el_type)
        h.add_edge(parent, code, 1)

    d = Dimension(name=DIM, hierarchies=[h])
    tm1.dimensions.update_or_create(d)

    cube_name = f"}}ElementAttributes_{DIM}"
    dims      = [DIM, f"}}ElementAttributes_{DIM}"]
    cells     = {}
    cells[('Total Cost Centres', 'Code & Desc')] = 'Total Cost Centres'
    cells[('Total Cost Centres', 'Desc')]        = 'Total Cost Centres'

    for code, desc, el_type, parent in STRUCTURE:
        if el_type == 'Numeric':
            cells[(code, 'Code & Desc')] = f"{code} {desc}"
            cells[(code, 'Desc')]        = desc
        else:
            cells[(code, 'Code & Desc')] = desc
            cells[(code, 'Desc')]        = desc

    tm1.cells.write_values(cube_name, cells, dimensions=dims)

    leaf_count = sum(1 for _, _, t, _ in STRUCTURE if t == 'Numeric')
    print(f"  ✓ {DIM} — {leaf_count} cost centres")


if __name__ == '__main__':
    with get_tm1_service() as tm1:
        main(tm1)
