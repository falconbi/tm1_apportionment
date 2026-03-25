"""
create_cst_apportionment_stage.py
Creates the CST Apportionment Stage dimension.
Two numeric elements: Pre Apportionment and Post Apportionment.
Called by build_cst_model.py.
"""

import sys
sys.path.insert(0, '.')
from TM1py.Objects import Dimension, Hierarchy
from tm1py_connect import get_tm1_service
from gbl_check import verify_gbl


def main(tm1):
    dim_name = 'CST Apportionment Stage'

    dim = Dimension(dim_name)
    hier = Hierarchy(dim_name, dim_name)

    hier.add_element('Pre Apportionment', 'Numeric')
    hier.add_element('Post Apportionment', 'Numeric')
    hier.add_element_attribute('Desc', 'Alias')

    dim.add_hierarchy(hier)
    tm1.dimensions.update_or_create(dim)

    attr_cube = f"}}ElementAttributes_{dim_name}"
    cells = {
        ('Pre Apportionment',  'Desc'): 'Pre Apportionment',
        ('Post Apportionment', 'Desc'): 'Post Apportionment',
    }
    tm1.cells.write_values(attr_cube, cells, dimensions=[dim_name, attr_cube])

    print(f"  ✓ {dim_name}")


if __name__ == '__main__':
    tm1 = get_tm1_service()
    verify_gbl(tm1)
    main(tm1)
    tm1.logout()
