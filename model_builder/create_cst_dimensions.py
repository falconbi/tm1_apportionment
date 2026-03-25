"""
create_cst_dimensions.py
Creates all CST dimensions (except CST Apportionment Stage).
Also adds 'Input' sentinel element to GBL Cost Centre.
Called by build_cst_model.py.

All attribute writes use write_values only:
    cube_name = f"}}ElementAttributes_{DIM}"
    dims      = [DIM, f"}}ElementAttributes_{DIM}"]
    cells     = {(element, 'AttrName'): value, ...}
    tm1.cells.write_values(cube_name, cells, dimensions=dims)
"""

import sys
sys.path.insert(0, '.')
from TM1py.Objects import Dimension, Hierarchy
from tm1py_connect import get_tm1_service
from gbl_check import verify_gbl


def build_coded_dim(tm1, dim_name, elements, consolidation):
    """
    Create/update a coded dimension with Code & Desc and Desc Alias attributes.
    Adds 'Input' sentinel element with weight 0 (excluded from totals).
    elements: list of (code, desc) tuples
    consolidation: name of single top-level consolidation element
    """
    dim  = Dimension(dim_name)
    hier = Hierarchy(dim_name, dim_name)

    hier.add_element(consolidation, 'Consolidated')
    for code, _ in elements:
        hier.add_element(code, 'Numeric')
    for code, _ in elements:
        hier.add_edge(consolidation, code, 1)

    # Input sentinel — used for cross-cube storage where this dim is not applicable.
    # Weight 0: element exists but does not contribute to consolidation totals.
    hier.add_element('Input', 'Numeric')
    hier.add_edge(consolidation, 'Input', 0)

    hier.add_element_attribute('Code & Desc', 'Alias')
    hier.add_element_attribute('Desc', 'Alias')

    dim.add_hierarchy(hier)
    tm1.dimensions.update_or_create(dim)

    cube_name = f"}}ElementAttributes_{dim_name}"
    dims      = [dim_name, f"}}ElementAttributes_{dim_name}"]
    cells     = {}
    for code, desc in elements:
        cells[(code, 'Code & Desc')] = f'{code} {desc}'
        cells[(code, 'Desc')]        = desc
    cells[('Input', 'Code & Desc')] = 'Input'
    cells[('Input', 'Desc')]        = 'Input'
    tm1.cells.write_values(cube_name, cells, dimensions=dims)

    print(f"  ✓ {dim_name} ({len(elements)} leaves + Input sentinel)")


def build_measure_dim(tm1, dim_name, elements):
    """
    Create/update a flat measure dimension with a Desc Alias attribute.
    elements: list of (name, elem_type) tuples — elem_type is 'Numeric' or 'String'
    """
    dim  = Dimension(dim_name)
    hier = Hierarchy(dim_name, dim_name)

    hier.add_element_attribute('Desc', 'Alias')
    for name, elem_type in elements:
        hier.add_element(name, elem_type)

    dim.add_hierarchy(hier)
    tm1.dimensions.update_or_create(dim)

    cube_name = f"}}ElementAttributes_{dim_name}"
    dims      = [dim_name, f"}}ElementAttributes_{dim_name}"]
    cells     = {(name, 'Desc'): name for name, _ in elements}
    tm1.cells.write_values(cube_name, cells, dimensions=dims)

    print(f"  ✓ {dim_name} ({len(elements)} elements)")


def add_gbl_cost_centre_input(tm1):
    """
    Adds 'Input' sentinel element to GBL Cost Centre.
    Required for Stage 1b and 2b Config cubes where Cost Centre is used
    as a sentinel dimension for driver rows.
    Element is added as an orphan (no consolidation edge) so it does not
    affect any existing GBL totals.
    """
    dim_name = 'GBL Cost Centre'
    dim      = tm1.dimensions.get(dim_name)
    hier     = dim.get_hierarchy(dim_name)

    if 'Input' in hier.elements:
        print(f"  - {dim_name} — Input already present, skipping")
        return

    hier.add_element('Input', 'Numeric')
    tm1.dimensions.update(dim)
    print(f"  ✓ {dim_name} — Input sentinel added")


# ─────────────────────────────────────────────────────────────
# CST Cost Pool  CP01–CP09
# ─────────────────────────────────────────────────────────────

def create_cst_cost_pool(tm1):
    build_coded_dim(tm1, 'CST Cost Pool', [
        ('CP01', 'Facilities'),
        ('CP02', 'Clinical Engineering'),
        ('CP03', 'Information Technology'),
        ('CP04', 'Human Resources'),
        ('CP05', 'Finance and Admin'),
        ('CP06', 'Sterilisation'),
        ('CP07', 'Patient Transport'),
        ('CP08', 'Catering'),
        ('CP09', 'Executive and Governance'),
    ], 'Total Cost Pools')


def create_cst_cost_pool_dest(tm1):
    build_coded_dim(tm1, 'CST Cost Pool Dest', [
        ('CP01', 'Facilities'),
        ('CP02', 'Clinical Engineering'),
        ('CP03', 'Information Technology'),
        ('CP04', 'Human Resources'),
        ('CP05', 'Finance and Admin'),
        ('CP06', 'Sterilisation'),
        ('CP07', 'Patient Transport'),
        ('CP08', 'Catering'),
        ('CP09', 'Executive and Governance'),
    ], 'Total Cost Pools')


# ─────────────────────────────────────────────────────────────
# CST Activity  A01–A11
# ─────────────────────────────────────────────────────────────

def create_cst_activity(tm1):
    build_coded_dim(tm1, 'CST Activity', [
        ('A01', 'Patient Admission'),
        ('A02', 'Surgical Preparation'),
        ('A03', 'Clinical Procedure'),
        ('A04', 'Patient Monitoring'),
        ('A05', 'Diagnostic Ordering'),
        ('A06', 'Diagnostic Reporting'),
        ('A07', 'Medication Management'),
        ('A08', 'Theatre Scheduling'),
        ('A09', 'Discharge Planning'),
        ('A10', 'Outpatient Coordination'),
        ('A11', 'Infection Prevention'),
    ], 'Total Activities')


def create_cst_activity_dest(tm1):
    build_coded_dim(tm1, 'CST Activity Dest', [
        ('A01', 'Patient Admission'),
        ('A02', 'Surgical Preparation'),
        ('A03', 'Clinical Procedure'),
        ('A04', 'Patient Monitoring'),
        ('A05', 'Diagnostic Ordering'),
        ('A06', 'Diagnostic Reporting'),
        ('A07', 'Medication Management'),
        ('A08', 'Theatre Scheduling'),
        ('A09', 'Discharge Planning'),
        ('A10', 'Outpatient Coordination'),
        ('A11', 'Infection Prevention'),
    ], 'Total Activities')


# ─────────────────────────────────────────────────────────────
# CST Service Line  SL01–SL08
# ─────────────────────────────────────────────────────────────

def create_cst_service_line(tm1):
    build_coded_dim(tm1, 'CST Service Line', [
        ('SL01', 'Emergency Department'),
        ('SL02', 'Elective Surgery'),
        ('SL03', 'Intensive Care Unit'),
        ('SL04', 'Outpatient Clinics'),
        ('SL05', 'Radiology'),
        ('SL06', 'Pathology Laboratory'),
        ('SL07', 'Maternity'),
        ('SL08', 'Allied Health'),
    ], 'Total Service Lines')


# ─────────────────────────────────────────────────────────────
# CST Reconciliation Check  RC01–RC06
# ─────────────────────────────────────────────────────────────

def create_cst_reconciliation_check(tm1):
    build_coded_dim(tm1, 'CST Reconciliation Check', [
        ('RC01', 'GL Input = Cost Pool'),
        ('RC02', 'Pool Reciprocal Balance'),
        ('RC03', 'Cost Pool = Activity'),
        ('RC04', 'Activity Reciprocal Balance'),
        ('RC05', 'Activity = Service Line'),
        ('RC06', 'GL Input = Service Line End to End'),
        ('VAL01', 'Driver Value Completeness'),
        ('VAL02', 'Driver Coverage'),
        ('VAL03', 'Driver SQL vs TM1'),
        ('VAL04', 'Account Config Coverage'),
    ], 'Total Reconciliation')


# ─────────────────────────────────────────────────────────────
# CST Driver
# ─────────────────────────────────────────────────────────────

def create_cst_driver(tm1):
    build_coded_dim(tm1, 'CST Driver', [
        ('FLOORSPACE',   'Floor Area (m2)'),
        ('HEADCOUNT',    'FTE Headcount'),
        ('ASSETVALUE',   'Asset Value'),
        ('POWERUSAGE',   'Power Usage (kWh)'),
        ('BEDDAYS',      'Patient Bed Days'),
        ('TRANSACTIONS', 'Transaction Count'),
    ], 'Total Drivers')


# ─────────────────────────────────────────────────────────────
# All measure dimensions
# ─────────────────────────────────────────────────────────────

def create_all_measure_dimensions(tm1):
    measures = {
        # ── Stage 1: Account → Pool ───────────────────────────────
        'CST Account Config Measure': [
            ('Amount',                  'Numeric'),
            ('Is Apportioned',          'Numeric'),
            ('Driver Percentage Share', 'Numeric'),
        ],
        'CST Account to Pool Apportionment Measure': [
            ('Amount',             'Numeric'),
            ('Apportionment Rate', 'Numeric'),
            ('Apportioned Amount', 'Numeric'),
        ],
        # ── Stage 1b: Pool → Pool (reciprocal) ───────────────────
        'CST Pool to Pool Config Measure': [
            ('Active',                  'Numeric'),   # 1 = relationship enabled; 0 or blank = excluded from Stage 1b
            ('Driver Value',            'Numeric'),
            ('Driver Description',      'String'),
            ('Driver Percentage Share', 'Numeric'),
            ('Apportioned Amount',      'Numeric'),
            ('Iteration Number',        'Numeric'),
        ],
        # ── Stage 2: Pool → Activity ──────────────────────────────
        'CST Pool Config Measure': [
            ('Pool to Activity Basis', 'String'),
            ('Driver Value',          'Numeric'),
            ('Driver Percentage Share', 'Numeric'),
        ],
        'CST Pool to Activity Apportionment Measure': [
            ('Amount',             'Numeric'),
            ('Settled Amount',     'Numeric'),
            ('Apportionment Rate', 'Numeric'),
            ('Apportioned Amount', 'Numeric'),
        ],
        # ── Stage 2b: Activity → Activity (reciprocal) ───────────
        'CST Activity to Activity Config Measure': [
            ('Driver Value',            'Numeric'),
            ('Driver Description',      'String'),
            ('Driver Percentage Share', 'Numeric'),
            ('Apportioned Amount',      'Numeric'),
            ('Iteration Number',        'Numeric'),
        ],
        # ── Stage 3: Activity → Service Line ─────────────────────
        'CST Activity Config Measure': [
            ('Activity to Service Line Basis', 'String'),
            ('Driver Value',                   'Numeric'),
            ('Input Volume',                   'Numeric'),
            ('Input Description',              'String'),
            ('Driver Percentage Share',        'Numeric'),
        ],
        'CST Activity to Service Line Apportionment Measure': [
            ('Amount',             'Numeric'),
            ('Apportionment Rate', 'Numeric'),
            ('Apportioned Amount', 'Numeric'),
            ('Per Unit',           'Numeric'),
        ],
        # ── Output / Audit ────────────────────────────────────────
        'CST Profit and Loss Report Measure': [
            ('Amount',                      'Numeric'),
            ('Variance to Budget',          'Numeric'),
            ('Variance Percent',            'Numeric'),
            ('ABC vs Traditional Variance', 'Numeric'),
        ],
        'CST Apportionment Reconciliation Measure': [
            ('Input Total',        'Numeric'),
            ('Output Total',       'Numeric'),
            ('Variance',           'Numeric'),
            ('Variance Percent',   'Numeric'),
            ('Status',             'String'),
            ('Message',            'String'),
            ('Stage 1b Complete',  'Numeric'),  # written by Python after Stage 1b — used as cross-cube flag in P2A rule
        ],
        'CST ETL Control Measure': [
            ('Status',       'String'),
            ('Period',       'String'),
            ('Version',      'String'),
            ('Force',        'Numeric'),
            ('Max Iter',     'Numeric'),
            ('Message',      'String'),
            ('Requested At', 'String'),
            ('Completed At', 'String'),
        ],
    }
    for dim_name, elements in measures.items():
        build_measure_dim(tm1, dim_name, elements)


# ─────────────────────────────────────────────────────────────
# CST ETL Job
# ─────────────────────────────────────────────────────────────

def create_cst_etl_job(tm1):
    dim  = Dimension('CST ETL Job')
    hier = Hierarchy('CST ETL Job', 'CST ETL Job')

    hier.add_element('Total ETL Jobs', 'Consolidated')
    for elem in ['Load GL', 'Load Drivers', 'Run Apportionment']:
        hier.add_element(elem, 'Numeric')
        hier.add_edge('Total ETL Jobs', elem, 1)

    dim.add_hierarchy(hier)
    tm1.dimensions.update_or_create(dim)
    print(f"  ✓ CST ETL Job (3 jobs)")


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main(tm1):
    print(f"\n{'─'*60}")
    print("  Creating CST dimensions...")
    print(f"{'─'*60}")

    # GBL extension — Input sentinel required for Config cubes
    add_gbl_cost_centre_input(tm1)

    create_cst_cost_pool(tm1)
    create_cst_cost_pool_dest(tm1)
    create_cst_activity(tm1)
    create_cst_activity_dest(tm1)
    create_cst_service_line(tm1)
    create_cst_reconciliation_check(tm1)
    create_cst_driver(tm1)
    create_cst_etl_job(tm1)
    create_all_measure_dimensions(tm1)

    print(f"  ✓ All CST dimensions created.")


if __name__ == '__main__':
    tm1 = get_tm1_service()
    verify_gbl(tm1)
    main(tm1)
    tm1.logout()
