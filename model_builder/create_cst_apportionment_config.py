"""
create_cst_apportionment_config.py
Creates the CST Apportionment Config cube.
Dimensions: CST Config Item × GBL Account × GBL Period × GBL Version ×
            CST Apportionment Config Measure
All measures are string type.
Called by build_cst_model.py.
"""

import sys
sys.path.insert(0, '.')
from TM1py.Objects import Cube
from tm1py_connect import get_tm1_service
from gbl_check import verify_gbl


def main(tm1):
    cube_name = 'CST Apportionment Config'
    dimensions = [
        'GBL Period',
        'GBL Version',
        'GBL Cost Centre',
        'GBL Account',
        'CST Cost Pool',
        'CST Apportionment Config Measure',
    ]

    if tm1.cubes.exists(cube_name):
        tm1.cubes.delete(cube_name)

    cube = Cube(cube_name, dimensions)
    tm1.cubes.create(cube)
    print(f"  ✓ {cube_name}")


if __name__ == '__main__':
    tm1 = get_tm1_service()
    verify_gbl(tm1)
    main(tm1)
    tm1.logout()
