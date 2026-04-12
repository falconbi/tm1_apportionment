"""
create_gbl_version.py
Builds the GBL Version dimension using TM1py.

Elements:   Actual, Budget, Forecast
Aliases:    Desc
Attributes: Is Snapshot, Start Period, Number of Rolling Months
            End Period is rule-derived from Start Period + Number of Rolling Months.
            Values are set as defaults here — edit directly in PAW as needed.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service
from TM1py.Objects import Dimension, Hierarchy, ElementAttribute

DIM = 'GBL Version'


def main(tm1):
    print(f"\n  Building {DIM}...")

    h = Hierarchy(name=DIM, dimension_name=DIM)

    h.add_element_attribute('Desc',                    'Alias')
    h.add_element_attribute('Is Snapshot',             'String')
    h.add_element_attribute('Start Period',            'String')
    h.add_element_attribute('End Period',              'String')   # rule-derived — do not write directly
    h.add_element_attribute('Number of Rolling Months','Numeric')
    h.add_element_attribute('Current Working',         'String')   # Y = active working version for views/reports

    versions = [
        ('Actual',   'Actual results'),
        ('Budget',   'Annual budget'),
        ('Forecast', 'Rolling forecast'),
    ]

    for el, desc in versions:
        h.add_element(el, 'Numeric')

    d = Dimension(name=DIM, hierarchies=[h])
    tm1.dimensions.update_or_create(d)

    # Ensure all attributes exist — update_or_create does not add new attributes
    # to an existing dimension so we add them individually if missing
    existing_attrs = tm1.elements.get_element_attribute_names(DIM, DIM)
    for attr_name, attr_type in [
        ('Desc',                     'Alias'),
        ('Is Snapshot',              'String'),
        ('Start Period',             'String'),
        ('End Period',               'String'),
        ('Number of Rolling Months', 'Numeric'),
        ('Current Working',          'String'),
    ]:
        if attr_name not in existing_attrs:
            tm1.elements.create_element_attribute(DIM, DIM, ElementAttribute(attr_name, attr_type))
            print(f"    Added attribute: {attr_name}")

    # Set Desc aliases
    cube_name = f"}}ElementAttributes_{DIM}"
    dims      = [DIM, f"}}ElementAttributes_{DIM}"]
    cells     = {(el, 'Desc'): desc for el, desc in versions}
    tm1.cells.write_values(cube_name, cells, dimensions=dims)

    # String attributes — write_through_unbound_process (CLAUDE.md Rule 1)
    string_defaults = {
        ('Actual',   'Is Snapshot'):     'N',
        ('Actual',   'Start Period'):    '2025-04',
        ('Actual',   'Current Working'): 'N',
        ('Budget',   'Is Snapshot'):     'N',
        ('Budget',   'Start Period'):    '2026-04',
        ('Budget',   'Current Working'): 'Y',
        ('Forecast', 'Is Snapshot'):     'N',
        ('Forecast', 'Start Period'):    '2026-04',
        ('Forecast', 'Current Working'): 'N',
    }
    tm1.cells.write_through_unbound_process(cube_name, string_defaults, dimensions=dims)

    # Numeric attributes
    numeric_defaults = {
        ('Actual',   'Number of Rolling Months'): 0,
        ('Budget',   'Number of Rolling Months'): 12,
        ('Forecast', 'Number of Rolling Months'): 18,
    }
    tm1.cells.write_values(cube_name, numeric_defaults, dimensions=dims)

    print(f"  ✓ {DIM} — {len(versions)} versions, attributes set")


if __name__ == '__main__':
    with get_tm1_service() as tm1:
        main(tm1)
