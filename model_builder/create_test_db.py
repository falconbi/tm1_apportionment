"""
create_test_db.py
Builds tests/data/cst_test_data.db — a SQLite database of sample data
aligned to the live TM1 model (GBL Account, CST Cost Pool, CST Activity,
CST Service Line, GBL Cost Centre codes).

Driver percentages sum to 100 per pool (pool_drivers) and per activity
(activity_drivers). GL input covers all 12 FY2025 Budget periods.

GBL Cost Centre codes (D001-D017):
  Clinical  : D001 Emergency Department, D002 Elective Surgery,
              D003 Intensive Care Unit, D004 Outpatient Clinics,
              D005 Radiology, D006 Pathology Laboratory,
              D007 Maternity, D008 Allied Health
  Admin     : D009 Finance and Administration, D010 Human Resources,
              D011 Information Technology, D012 Executive and Governance
  Support   : D013 Facility Management, D014 Clinical Engineering,
              D015 Sterilisation Services, D016 Patient Transport,
              D017 Catering Services

Run standalone:
    python3 model_builder/create_test_db.py
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / 'tests' / 'data' / 'cst_test_data.db'


# ── Reference data ──────────────────────────────────────────────────────────

# (code, desc, account_type, cost_pool)
# account_type: Revenue | Direct Costs | Overhead | Allocated Overhead
# cost_pool: which CST Cost Pool this account feeds — NULL for non-overhead
GL_ACCOUNTS = [
    # Revenue
    ('4001', 'Inpatient Revenue',               'Revenue',            None),
    ('4002', 'Outpatient Revenue',              'Revenue',            None),
    ('4003', 'Radiology Revenue',               'Revenue',            None),
    ('4004', 'Pathology Revenue',               'Revenue',            None),
    ('4005', 'Other Revenue',                   'Revenue',            None),
    # Direct Costs
    ('5001', 'Direct Labour',                   'Direct Costs',       None),
    ('5002', 'Direct Materials',                'Direct Costs',       None),
    ('5003', 'Direct Supplies',                 'Direct Costs',       None),
    # Overhead — mapped to cost pools
    ('6001', 'Indirect Nursing Salaries',       'Overhead',           'CP01'),
    ('6002', 'Medical Administration Salaries', 'Overhead',           'CP05'),
    ('6003', 'Building Depreciation',           'Overhead',           'CP01'),
    ('6004', 'Rent and Rates',                  'Overhead',           'CP01'),
    ('6005', 'Cleaning and Waste',              'Overhead',           'CP01'),
    ('6006', 'Medical Equipment Depreciation',  'Overhead',           'CP02'),
    ('6007', 'Equipment Maintenance',           'Overhead',           'CP02'),
    ('6008', 'IT Infrastructure',               'Overhead',           'CP03'),
    ('6009', 'Software Licences',               'Overhead',           'CP03'),
    ('6010', 'IT Helpdesk',                     'Overhead',           'CP03'),
    ('6011', 'Recruitment Costs',               'Overhead',           'CP04'),
    ('6012', 'Training and Development',        'Overhead',           'CP04'),
    ('6013', 'HR Administration',               'Overhead',           'CP04'),
    ('6014', 'Finance Team Salaries',           'Overhead',           'CP05'),
    ('6015', 'Payroll Processing',              'Overhead',           'CP05'),
    ('6016', 'Accounts Payable',                'Overhead',           'CP05'),
    ('6017', 'Autoclave Operation',             'Overhead',           'CP06'),
    ('6018', 'Sterilisation Materials',         'Overhead',           'CP06'),
    ('6019', 'Orderly Salaries',                'Overhead',           'CP07'),
    ('6020', 'Patient Transfer Equipment',      'Overhead',           'CP07'),
    ('6021', 'Catering Salaries',               'Overhead',           'CP08'),
    ('6022', 'Food and Beverage',               'Overhead',           'CP08'),
    ('6023', 'Executive Salaries',              'Overhead',           'CP09'),
    ('6024', 'Board Costs',                     'Overhead',           'CP09'),
    ('6025', 'Legal and Compliance',            'Overhead',           'CP09'),
    ('6026', 'Accreditation Costs',             'Overhead',           'CP09'),
    # Allocated Overhead (already apportioned — no cost pool input)
    ('7001', 'Facility Management Allocated',      'Allocated Overhead', None),
    ('7002', 'Clinical Engineering Allocated',     'Allocated Overhead', None),
    ('7003', 'Information Technology Allocated',   'Allocated Overhead', None),
    ('7004', 'Human Resources Allocated',          'Allocated Overhead', None),
    ('7005', 'Finance and Admin Allocated',        'Allocated Overhead', None),
    ('7006', 'Sterilisation Allocated',            'Allocated Overhead', None),
    ('7007', 'Patient Transport Allocated',        'Allocated Overhead', None),
    ('7008', 'Catering Allocated',                 'Allocated Overhead', None),
    ('7009', 'Executive and Governance Allocated', 'Allocated Overhead', None),
]

COST_POOLS = [
    ('CP01', 'Facilities'),
    ('CP02', 'Clinical Engineering'),
    ('CP03', 'Information Technology'),
    ('CP04', 'Human Resources'),
    ('CP05', 'Finance and Admin'),
    ('CP06', 'Sterilisation'),
    ('CP07', 'Patient Transport'),
    ('CP08', 'Catering'),
    ('CP09', 'Executive and Governance'),
]

ACTIVITIES = [
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
]

SERVICE_LINES = [
    ('SL01', 'Emergency Department'),
    ('SL02', 'Elective Surgery'),
    ('SL03', 'Intensive Care Unit'),
    ('SL04', 'Outpatient Clinics'),
    ('SL05', 'Radiology'),
    ('SL06', 'Pathology Laboratory'),
    ('SL07', 'Maternity'),
    ('SL08', 'Allied Health'),
]


# ── Driver tables ────────────────────────────────────────────────────────────
# Each row: (pool_code, activity_code, driver_value, driver_percentage_share)
# driver_percentage_share sums to 100.00 per pool_code.
# driver_value = driver_percentage_share * 100 (e.g. square metres, FTE, transactions)

POOL_DRIVERS = [
    # CP01 Facilities — space/bed-day weighting
    ('CP01','A01',1000,10.00), ('CP01','A02',1200,12.00), ('CP01','A03',1500,15.00),
    ('CP01','A04',1300,13.00), ('CP01','A05', 500, 5.00), ('CP01','A06', 500, 5.00),
    ('CP01','A07', 800, 8.00), ('CP01','A08',1000,10.00), ('CP01','A09', 700, 7.00),
    ('CP01','A10', 800, 8.00), ('CP01','A11', 700, 7.00),
    # CP02 Clinical Engineering — equipment hours
    ('CP02','A01', 500, 5.00), ('CP02','A02',1500,15.00), ('CP02','A03',2000,20.00),
    ('CP02','A04',1000,10.00), ('CP02','A05',1200,12.00), ('CP02','A06',1200,12.00),
    ('CP02','A07', 500, 5.00), ('CP02','A08', 800, 8.00), ('CP02','A09', 300, 3.00),
    ('CP02','A10', 500, 5.00), ('CP02','A11', 500, 5.00),
    # CP03 Information Technology — system transactions
    ('CP03','A01', 800, 8.00), ('CP03','A02', 500, 5.00), ('CP03','A03', 800, 8.00),
    ('CP03','A04',1000,10.00), ('CP03','A05',1500,15.00), ('CP03','A06',1500,15.00),
    ('CP03','A07',1000,10.00), ('CP03','A08',1200,12.00), ('CP03','A09', 700, 7.00),
    ('CP03','A10', 800, 8.00), ('CP03','A11', 200, 2.00),
    # CP04 Human Resources — headcount
    ('CP04','A01',1000,10.00), ('CP04','A02',1000,10.00), ('CP04','A03',1000,10.00),
    ('CP04','A04',1000,10.00), ('CP04','A05', 800, 8.00), ('CP04','A06', 800, 8.00),
    ('CP04','A07',1000,10.00), ('CP04','A08', 800, 8.00), ('CP04','A09', 800, 8.00),
    ('CP04','A10',1000,10.00), ('CP04','A11', 800, 8.00),
    # CP05 Finance and Admin — invoice/transaction count
    ('CP05','A01',1200,12.00), ('CP05','A02', 800, 8.00), ('CP05','A03', 800, 8.00),
    ('CP05','A04',1000,10.00), ('CP05','A05', 800, 8.00), ('CP05','A06', 800, 8.00),
    ('CP05','A07',1000,10.00), ('CP05','A08', 800, 8.00), ('CP05','A09',1000,10.00),
    ('CP05','A10',1000,10.00), ('CP05','A11', 800, 8.00),
    # CP06 Sterilisation — tray count
    ('CP06','A01', 500, 5.00), ('CP06','A02',2500,25.00), ('CP06','A03',3000,30.00),
    ('CP06','A04', 500, 5.00), ('CP06','A05', 500, 5.00), ('CP06','A06', 500, 5.00),
    ('CP06','A07', 500, 5.00), ('CP06','A08',1000,10.00), ('CP06','A09', 500, 5.00),
    ('CP06','A10', 300, 3.00), ('CP06','A11', 200, 2.00),
    # CP07 Patient Transport — patient moves
    ('CP07','A01',1500,15.00), ('CP07','A02',1000,10.00), ('CP07','A03', 500, 5.00),
    ('CP07','A04',1500,15.00), ('CP07','A05', 500, 5.00), ('CP07','A06', 500, 5.00),
    ('CP07','A07', 500, 5.00), ('CP07','A08', 500, 5.00), ('CP07','A09',2000,20.00),
    ('CP07','A10',1000,10.00), ('CP07','A11', 500, 5.00),
    # CP08 Catering — meal count
    ('CP08','A01',1000,10.00), ('CP08','A02',1000,10.00), ('CP08','A03',1000,10.00),
    ('CP08','A04',1500,15.00), ('CP08','A05', 500, 5.00), ('CP08','A06', 500, 5.00),
    ('CP08','A07', 500, 5.00), ('CP08','A08', 500, 5.00), ('CP08','A09',1500,15.00),
    ('CP08','A10',1000,10.00), ('CP08','A11',1000,10.00),
    # CP09 Executive and Governance — FTE
    ('CP09','A01',1000,10.00), ('CP09','A02',1000,10.00), ('CP09','A03',1000,10.00),
    ('CP09','A04',1000,10.00), ('CP09','A05', 800, 8.00), ('CP09','A06', 800, 8.00),
    ('CP09','A07', 800, 8.00), ('CP09','A08',1000,10.00), ('CP09','A09', 800, 8.00),
    ('CP09','A10',1000,10.00), ('CP09','A11', 800, 8.00),
]

# Each row: (activity_code, service_line_code, driver_value, driver_percentage_share)
# driver_percentage_share sums to 100.00 per activity_code.
# driver_value = encounters / procedures per service line for that activity

ACTIVITY_DRIVERS = [
    # A01 Patient Admission — admissions by service line
    ('A01','SL01',250,25.00), ('A01','SL02',150,15.00), ('A01','SL03',100,10.00),
    ('A01','SL04',150,15.00), ('A01','SL05', 50, 5.00), ('A01','SL06', 50, 5.00),
    ('A01','SL07',150,15.00), ('A01','SL08',100,10.00),
    # A02 Surgical Preparation — surgical cases
    ('A02','SL01', 50, 5.00), ('A02','SL02',400,40.00), ('A02','SL03',200,20.00),
    ('A02','SL04', 50, 5.00), ('A02','SL05', 50, 5.00), ('A02','SL06', 50, 5.00),
    ('A02','SL07',150,15.00), ('A02','SL08', 50, 5.00),
    # A03 Clinical Procedure — procedures performed
    ('A03','SL01',150,15.00), ('A03','SL02',300,30.00), ('A03','SL03',250,25.00),
    ('A03','SL04',100,10.00), ('A03','SL05', 50, 5.00), ('A03','SL06', 50, 5.00),
    ('A03','SL07', 50, 5.00), ('A03','SL08', 50, 5.00),
    # A04 Patient Monitoring — monitored patient days
    ('A04','SL01',200,20.00), ('A04','SL02',100,10.00), ('A04','SL03',300,30.00),
    ('A04','SL04',100,10.00), ('A04','SL05', 50, 5.00), ('A04','SL06', 50, 5.00),
    ('A04','SL07',100,10.00), ('A04','SL08',100,10.00),
    # A05 Diagnostic Ordering — orders placed
    ('A05','SL01',200,20.00), ('A05','SL02',150,15.00), ('A05','SL03',150,15.00),
    ('A05','SL04',200,20.00), ('A05','SL05',100,10.00), ('A05','SL06',100,10.00),
    ('A05','SL07', 50, 5.00), ('A05','SL08', 50, 5.00),
    # A06 Diagnostic Reporting — reports issued
    ('A06','SL01',150,15.00), ('A06','SL02',150,15.00), ('A06','SL03',150,15.00),
    ('A06','SL04',150,15.00), ('A06','SL05',200,20.00), ('A06','SL06',150,15.00),
    ('A06','SL07', 30, 3.00), ('A06','SL08', 20, 2.00),
    # A07 Medication Management — medication episodes
    ('A07','SL01',200,20.00), ('A07','SL02',150,15.00), ('A07','SL03',200,20.00),
    ('A07','SL04',150,15.00), ('A07','SL05', 50, 5.00), ('A07','SL06', 50, 5.00),
    ('A07','SL07',100,10.00), ('A07','SL08',100,10.00),
    # A08 Theatre Scheduling — theatre sessions
    ('A08','SL01', 50, 5.00), ('A08','SL02',500,50.00), ('A08','SL03',150,15.00),
    ('A08','SL04', 50, 5.00), ('A08','SL05', 50, 5.00), ('A08','SL06', 50, 5.00),
    ('A08','SL07',100,10.00), ('A08','SL08', 50, 5.00),
    # A09 Discharge Planning — discharges
    ('A09','SL01',250,25.00), ('A09','SL02',200,20.00), ('A09','SL03',150,15.00),
    ('A09','SL04',150,15.00), ('A09','SL05', 50, 5.00), ('A09','SL06', 50, 5.00),
    ('A09','SL07',100,10.00), ('A09','SL08', 50, 5.00),
    # A10 Outpatient Coordination — outpatient encounters
    ('A10','SL01', 50, 5.00), ('A10','SL02', 50, 5.00), ('A10','SL03', 50, 5.00),
    ('A10','SL04',500,50.00), ('A10','SL05',100,10.00), ('A10','SL06',100,10.00),
    ('A10','SL07', 50, 5.00), ('A10','SL08',100,10.00),
    # A11 Infection Prevention — infection control audits / bed-days
    ('A11','SL01',150,15.00), ('A11','SL02',150,15.00), ('A11','SL03',200,20.00),
    ('A11','SL04',100,10.00), ('A11','SL05', 50, 5.00), ('A11','SL06', 50, 5.00),
    ('A11','SL07',150,15.00), ('A11','SL08',150,15.00),
]


# ── GL Input ─────────────────────────────────────────────────────────────────
# Realistic monthly hospital financials (amounts in $000s).
# Revenue and Direct Costs spread across clinical departments D001–D008.
# Overhead accounts allocated to their home support department D009–D017.
# D009 Clinical Support   D010 Medical Administration  D011 Facilities
# D012 Clinical Eng       D013 Information Technology  D014 Human Resources
# D015 Finance and Admin  D016 Sterilisation           D017 Patient Transport

def _gl_input_rows():
    # Monthly variance factors — indexed by position within each period list.
    # Budget (12 months): Revenue softer start, peaks mid-year, slight Q4 dip.
    rev_bdgt  = [0.94, 0.97, 1.00, 1.04, 1.06, 1.05, 1.03, 1.02, 0.98, 0.96, 0.97, 0.98]
    cost_bdgt = [0.98, 0.99, 1.00, 1.01, 1.00, 1.01, 1.02, 1.01, 1.00, 0.99, 0.99, 1.02]
    oh_bdgt   = [1.00, 1.00, 1.00, 1.00, 1.00, 1.01, 1.01, 1.01, 1.01, 1.02, 1.02, 1.03]
    # Forecast (18 months): base amounts grown +5% rev / +3% cost / +2% overhead vs Budget.
    rev_fcst  = [round(1.05 * f, 4) for f in
                 [0.96, 0.98, 1.00, 1.03, 1.05, 1.04, 1.02, 1.01, 0.97, 0.95, 0.96, 0.97,
                  0.97, 0.96, 0.98, 1.00, 1.01, 0.99]]
    cost_fcst = [round(1.03 * f, 4) for f in
                 [0.99, 1.00, 1.01, 1.01, 1.00, 1.01, 1.02, 1.01, 1.00, 0.99, 0.99, 1.01,
                  1.01, 1.02, 1.02, 1.01, 1.01, 1.02]]
    oh_fcst   = [round(1.02 * f, 4) for f in
                 [1.00, 1.01, 1.01, 1.01, 1.01, 1.02, 1.02, 1.02, 1.02, 1.03, 1.03, 1.03,
                  1.03, 1.03, 1.04, 1.04, 1.04, 1.04]]

    rows = []

    # Revenue 4001–4005 — clinical depts D001–D006
    revenue = [
        ('4001', {'D001':1820,'D002':1340,'D003':960,'D004':780,'D005':420}),
        ('4002', {'D001': 680,'D002': 520,'D003':310,'D004':280,'D005':190}),
        ('4003', {'D005': 580}),
        ('4004', {'D006': 340}),
        ('4005', {'D001': 95,'D002': 85,'D003': 70,'D004': 65,'D005': 55,
                  'D006': 60,'D007': 45,'D008': 40}),
    ]
    for periods, version, rev_f, cost_f, oh_f in [
        (_BUDGET_PERIODS,   'Budget',   rev_bdgt,  cost_bdgt,  oh_bdgt),
        (_FORECAST_PERIODS, 'Forecast', rev_fcst,  cost_fcst,  oh_fcst),
    ]:
        for i, period in enumerate(periods):
            for acct, dept_amounts in revenue:
                for dept, amt in dept_amounts.items():
                    rows.append((period, version, acct, dept, round(amt * rev_f[i], 2)))

        # Direct Costs 5001–5003 — clinical depts D001–D008
        direct = [
            ('5001', {'D001':620,'D002':480,'D003':390,'D004':340,'D005':280,
                      'D006':220,'D007':195,'D008':170}),
            ('5002', {'D001':210,'D002':175,'D003':140,'D004':120,'D005':100,
                      'D006': 90,'D007': 80,'D008': 70}),
            ('5003', {'D001': 95,'D002': 80,'D003': 65,'D004': 60,'D005': 50,
                      'D006': 45,'D007': 40,'D008': 35}),
        ]
        for i, period in enumerate(periods):
            for acct, dept_amounts in direct:
                for dept, amt in dept_amounts.items():
                    rows.append((period, version, acct, dept, round(amt * cost_f[i], 2)))

        # Overhead 6001–6026 — each account appears in at least 3 cost centres
        # with varying amounts (primary home dept + 2 secondary depts).
        # Admin:   D009 Finance & Admin, D010 Human Resources,
        #          D011 Information Technology, D012 Executive & Governance
        # Support: D013 Facility Management, D014 Clinical Engineering,
        #          D015 Sterilisation, D016 Patient Transport, D017 Catering
        overhead = [
            # CP01 Facilities
            ('6001', {'D013': 185.0, 'D009':  75.0, 'D010':  55.0}),  # Indirect Nursing
            ('6003', {'D013': 310.0, 'D009':  95.0, 'D011':  70.0}),  # Building Depreciation
            ('6004', {'D013': 145.0, 'D011':  50.0, 'D012':  35.0}),  # Rent and Rates
            ('6005', {'D013':  95.0, 'D014':  40.0, 'D015':  25.0}),  # Cleaning and Waste
            # CP02 Clinical Engineering
            ('6006', {'D014': 260.0, 'D011':  80.0, 'D012':  45.0}),  # Medical Equipment Depreciation
            ('6007', {'D014': 175.0, 'D013':  65.0, 'D015':  40.0}),  # Equipment Maintenance
            # CP03 Information Technology
            ('6008', {'D011': 340.0, 'D009': 110.0, 'D013':  75.0}),  # IT Infrastructure
            ('6009', {'D011': 125.0, 'D009':  55.0, 'D010':  40.0}),  # Software Licences
            ('6010', {'D011':  85.0, 'D009':  35.0, 'D012':  25.0}),  # IT Helpdesk
            # CP04 Human Resources
            ('6011', {'D010':  75.0, 'D009':  30.0, 'D012':  20.0}),  # Recruitment Costs
            ('6012', {'D010':  95.0, 'D009':  40.0, 'D011':  30.0}),  # Training and Development
            ('6013', {'D010': 130.0, 'D009':  50.0, 'D012':  35.0}),  # HR Administration
            # CP05 Finance and Admin
            ('6002', {'D009': 220.0, 'D010':  85.0, 'D012':  60.0}),  # Medical Administration Salaries
            ('6014', {'D009': 285.0, 'D010':  90.0, 'D011':  55.0}),  # Finance Team Salaries
            ('6015', {'D009':  70.0, 'D010':  28.0, 'D013':  18.0}),  # Payroll Processing
            ('6016', {'D009':  55.0, 'D010':  22.0, 'D012':  15.0}),  # Accounts Payable
            # CP06 Sterilisation
            ('6017', {'D015':  60.0, 'D013':  22.0, 'D014':  15.0}),  # Autoclave Operation
            ('6018', {'D015':  45.0, 'D013':  18.0, 'D014':  12.0}),  # Sterilisation Materials
            # CP07 Patient Transport
            ('6019', {'D016': 155.0, 'D013':  55.0, 'D009':  35.0}),  # Orderly Salaries
            ('6020', {'D016':  80.0, 'D014':  30.0, 'D013':  20.0}),  # Patient Transfer Equipment
            # CP08 Catering
            ('6021', {'D017': 165.0, 'D013':  55.0, 'D009':  30.0}),  # Catering Salaries
            ('6022', {'D017':  90.0, 'D013':  32.0, 'D015':  22.0}),  # Food and Beverage
            # CP09 Executive and Governance
            ('6023', {'D012': 310.0, 'D009':  95.0, 'D010':  65.0}),  # Executive Salaries
            ('6024', {'D012':  55.0, 'D009':  20.0, 'D011':  12.0}),  # Board Costs
            ('6025', {'D012':  65.0, 'D009':  25.0, 'D013':  15.0}),  # Legal and Compliance
            ('6026', {'D012':  40.0, 'D009':  15.0, 'D014':  10.0}),  # Accreditation Costs
        ]
        for i, period in enumerate(periods):
            for acct, dept_amounts in overhead:
                for dept, amt in dept_amounts.items():
                    rows.append((period, version, acct, dept, round(amt * oh_f[i], 2)))

    return rows


# ── Apportionment Config ─────────────────────────────────────────────────────
# (account_code, cost_centre_code, cost_pool_code, apportionment_pct)
# Most overhead accounts: 100% to their designated pool.
# 9 accounts split across 2-3 pools (at least 8 required).

APPOR_CONFIG_STATIC = [
    # ── Simple 100% mappings — all cost centres for each account ─────────────
    ('6003', 'D013', 'CP01', 100.0),  # Building Depreciation (home)
    ('6003', 'D009', 'CP01', 100.0),  # Building Depreciation (D009)
    ('6003', 'D011', 'CP01', 100.0),  # Building Depreciation (D011)
    ('6004', 'D013', 'CP01', 100.0),  # Rent and Rates (home)
    ('6004', 'D011', 'CP01', 100.0),  # Rent and Rates (D011)
    ('6004', 'D012', 'CP01', 100.0),  # Rent and Rates (D012)
    ('6006', 'D014', 'CP02', 100.0),  # Medical Equipment Depreciation (home)
    ('6006', 'D011', 'CP02', 100.0),  # Medical Equipment Depreciation (D011)
    ('6006', 'D012', 'CP02', 100.0),  # Medical Equipment Depreciation (D012)
    ('6008', 'D011', 'CP03', 100.0),  # IT Infrastructure (home)
    ('6008', 'D009', 'CP03', 100.0),  # IT Infrastructure (D009)
    ('6008', 'D013', 'CP03', 100.0),  # IT Infrastructure (D013)
    ('6010', 'D011', 'CP03', 100.0),  # IT Helpdesk (home)
    ('6010', 'D009', 'CP03', 100.0),  # IT Helpdesk (D009)
    ('6010', 'D012', 'CP03', 100.0),  # IT Helpdesk (D012)
    ('6011', 'D010', 'CP04', 100.0),  # Recruitment Costs (home)
    ('6011', 'D009', 'CP04', 100.0),  # Recruitment Costs (D009)
    ('6011', 'D012', 'CP04', 100.0),  # Recruitment Costs (D012)
    ('6013', 'D010', 'CP04', 100.0),  # HR Administration (home)
    ('6013', 'D009', 'CP04', 100.0),  # HR Administration (D009)
    ('6013', 'D012', 'CP04', 100.0),  # HR Administration (D012)
    ('6014', 'D009', 'CP05', 100.0),  # Finance Team Salaries (home)
    ('6014', 'D010', 'CP05', 100.0),  # Finance Team Salaries (D010)
    ('6014', 'D011', 'CP05', 100.0),  # Finance Team Salaries (D011)
    ('6016', 'D009', 'CP05', 100.0),  # Accounts Payable (home)
    ('6016', 'D010', 'CP05', 100.0),  # Accounts Payable (D010)
    ('6016', 'D012', 'CP05', 100.0),  # Accounts Payable (D012)
    ('6017', 'D015', 'CP06', 100.0),  # Autoclave Operation (home)
    ('6017', 'D013', 'CP06', 100.0),  # Autoclave Operation (D013)
    ('6017', 'D014', 'CP06', 100.0),  # Autoclave Operation (D014)
    ('6018', 'D015', 'CP06', 100.0),  # Sterilisation Materials (home)
    ('6018', 'D013', 'CP06', 100.0),  # Sterilisation Materials (D013)
    ('6018', 'D014', 'CP06', 100.0),  # Sterilisation Materials (D014)
    ('6019', 'D016', 'CP07', 100.0),  # Orderly Salaries (home)
    ('6019', 'D013', 'CP07', 100.0),  # Orderly Salaries (D013)
    ('6019', 'D009', 'CP07', 100.0),  # Orderly Salaries (D009)
    ('6020', 'D016', 'CP07', 100.0),  # Patient Transfer Equipment (home)
    ('6020', 'D014', 'CP07', 100.0),  # Patient Transfer Equipment (D014)
    ('6020', 'D013', 'CP07', 100.0),  # Patient Transfer Equipment (D013)
    ('6022', 'D017', 'CP08', 100.0),  # Food and Beverage (home)
    ('6022', 'D013', 'CP08', 100.0),  # Food and Beverage (D013)
    ('6022', 'D015', 'CP08', 100.0),  # Food and Beverage (D015)
    ('6024', 'D012', 'CP09', 100.0),  # Board Costs (home)
    ('6024', 'D009', 'CP09', 100.0),  # Board Costs (D009)
    ('6024', 'D011', 'CP09', 100.0),  # Board Costs (D011)
    ('6025', 'D012', 'CP09', 100.0),  # Legal and Compliance (home)
    ('6025', 'D009', 'CP09', 100.0),  # Legal and Compliance (D009)
    ('6025', 'D013', 'CP09', 100.0),  # Legal and Compliance (D013)
    ('6026', 'D012', 'CP09', 100.0),  # Accreditation Costs (home)
    ('6026', 'D009', 'CP09', 100.0),  # Accreditation Costs (D009)
    ('6026', 'D014', 'CP09', 100.0),  # Accreditation Costs (D014)
    # ── Split mappings (9 accounts across multiple pools) ────────────────────
    ('6001', 'D013', 'CP01', 60.0),   # Indirect Nursing → Facilities
    ('6001', 'D013', 'CP04', 40.0),   # Indirect Nursing → HR
    ('6001', 'D009', 'CP01', 60.0),   # Indirect Nursing (D009) → Facilities
    ('6001', 'D009', 'CP04', 40.0),   # Indirect Nursing (D009) → HR
    ('6001', 'D010', 'CP01', 60.0),   # Indirect Nursing (D010) → Facilities
    ('6001', 'D010', 'CP04', 40.0),   # Indirect Nursing (D010) → HR
    ('6002', 'D009', 'CP05', 70.0),   # Medical Admin → Finance and Admin
    ('6002', 'D009', 'CP04', 30.0),   # Medical Admin → HR
    ('6002', 'D010', 'CP05', 70.0),   # Medical Admin (D010) → Finance and Admin
    ('6002', 'D010', 'CP04', 30.0),   # Medical Admin (D010) → HR
    ('6002', 'D012', 'CP05', 70.0),   # Medical Admin (D012) → Finance and Admin
    ('6002', 'D012', 'CP04', 30.0),   # Medical Admin (D012) → HR
    ('6005', 'D013', 'CP01', 80.0),   # Cleaning and Waste → Facilities
    ('6005', 'D013', 'CP06', 20.0),   # Cleaning and Waste → Sterilisation
    ('6005', 'D014', 'CP01', 80.0),   # Cleaning and Waste (D014) → Facilities
    ('6005', 'D014', 'CP06', 20.0),   # Cleaning and Waste (D014) → Sterilisation
    ('6005', 'D015', 'CP01', 80.0),   # Cleaning and Waste (D015) → Facilities
    ('6005', 'D015', 'CP06', 20.0),   # Cleaning and Waste (D015) → Sterilisation
    ('6007', 'D014', 'CP02', 75.0),   # Equipment Maintenance → Clinical Eng
    ('6007', 'D014', 'CP01', 25.0),   # Equipment Maintenance → Facilities
    ('6007', 'D013', 'CP02', 75.0),   # Equipment Maintenance (D013) → Clinical Eng
    ('6007', 'D013', 'CP01', 25.0),   # Equipment Maintenance (D013) → Facilities
    ('6007', 'D015', 'CP02', 75.0),   # Equipment Maintenance (D015) → Clinical Eng
    ('6007', 'D015', 'CP01', 25.0),   # Equipment Maintenance (D015) → Facilities
    ('6009', 'D011', 'CP03', 80.0),   # Software Licences → IT
    ('6009', 'D011', 'CP09', 20.0),   # Software Licences → Executive
    ('6009', 'D009', 'CP03', 80.0),   # Software Licences (D009) → IT
    ('6009', 'D009', 'CP09', 20.0),   # Software Licences (D009) → Executive
    ('6009', 'D010', 'CP03', 80.0),   # Software Licences (D010) → IT
    ('6009', 'D010', 'CP09', 20.0),   # Software Licences (D010) → Executive
    ('6012', 'D010', 'CP04', 70.0),   # Training and Development → HR
    ('6012', 'D010', 'CP05', 30.0),   # Training and Development → Finance
    ('6012', 'D009', 'CP04', 70.0),   # Training and Development (D009) → HR
    ('6012', 'D009', 'CP05', 30.0),   # Training and Development (D009) → Finance
    ('6012', 'D011', 'CP04', 70.0),   # Training and Development (D011) → HR
    ('6012', 'D011', 'CP05', 30.0),   # Training and Development (D011) → Finance
    ('6015', 'D009', 'CP05', 80.0),   # Payroll Processing → Finance
    ('6015', 'D009', 'CP04', 20.0),   # Payroll Processing → HR
    ('6015', 'D010', 'CP05', 80.0),   # Payroll Processing (D010) → Finance
    ('6015', 'D010', 'CP04', 20.0),   # Payroll Processing (D010) → HR
    ('6015', 'D013', 'CP05', 80.0),   # Payroll Processing (D013) → Finance
    ('6015', 'D013', 'CP04', 20.0),   # Payroll Processing (D013) → HR
    ('6021', 'D017', 'CP08', 85.0),   # Catering Salaries → Catering
    ('6021', 'D017', 'CP01', 15.0),   # Catering Salaries → Facilities
    ('6021', 'D013', 'CP08', 85.0),   # Catering Salaries (D013) → Catering
    ('6021', 'D013', 'CP01', 15.0),   # Catering Salaries (D013) → Facilities
    ('6021', 'D009', 'CP08', 85.0),   # Catering Salaries (D009) → Catering
    ('6021', 'D009', 'CP01', 15.0),   # Catering Salaries (D009) → Facilities
    ('6023', 'D012', 'CP09', 80.0),   # Executive Salaries → Executive
    ('6023', 'D012', 'CP04', 10.0),   # Executive Salaries → HR
    ('6023', 'D012', 'CP05', 10.0),   # Executive Salaries → Finance
    ('6023', 'D009', 'CP09', 80.0),   # Executive Salaries (D009) → Executive
    ('6023', 'D009', 'CP04', 10.0),   # Executive Salaries (D009) → HR
    ('6023', 'D009', 'CP05', 10.0),   # Executive Salaries (D009) → Finance
    ('6023', 'D010', 'CP09', 80.0),   # Executive Salaries (D010) → Executive
    ('6023', 'D010', 'CP04', 10.0),   # Executive Salaries (D010) → HR
    ('6023', 'D010', 'CP05', 10.0),   # Executive Salaries (D010) → Finance
]


# ── Pool to Pool Driver Input ─────────────────────────────────────────────────
# (pool_code, pool_dest_code, driver_value, driver_description)
# Three source pools: CP01 (Facilities), CP03 (IT), CP04 (HR).
# Percentages sum to 100 per source pool across all destinations.

def _pool_to_pool_input_rows():
    _p2p_static = [
        # CP01 Facilities → all other pools by floor area (m2)
        ('CP01','CP02', 250.0, 'Floor Area (m2)'),
        ('CP01','CP03', 180.0, 'Floor Area (m2)'),
        ('CP01','CP04', 120.0, 'Floor Area (m2)'),
        ('CP01','CP05', 200.0, 'Floor Area (m2)'),
        ('CP01','CP06',  80.0, 'Floor Area (m2)'),
        ('CP01','CP07', 150.0, 'Floor Area (m2)'),
        ('CP01','CP08', 160.0, 'Floor Area (m2)'),
        ('CP01','CP09',  60.0, 'Floor Area (m2)'),
        # CP03 IT → admin pools by IT resource units
        ('CP03','CP01', 150.0, 'IT Resource Units'),
        ('CP03','CP02', 200.0, 'IT Resource Units'),
        ('CP03','CP04', 250.0, 'IT Resource Units'),
        ('CP03','CP05', 200.0, 'IT Resource Units'),
        # CP04 HR → all other pools by FTE headcount
        ('CP04','CP01', 100.0, 'FTE Headcount'),
        ('CP04','CP02', 110.0, 'FTE Headcount'),
        ('CP04','CP03', 130.0, 'FTE Headcount'),
        ('CP04','CP05', 160.0, 'FTE Headcount'),
        ('CP04','CP06',  90.0, 'FTE Headcount'),
        ('CP04','CP07', 100.0, 'FTE Headcount'),
        ('CP04','CP08', 110.0, 'FTE Headcount'),
        ('CP04','CP09', 100.0, 'FTE Headcount'),
    ]
    rows = []
    for period in _BUDGET_PERIODS:
        for pool, dest, val, desc in _p2p_static:
            rows.append((period, 'Budget', pool, dest, val, desc))
    for period in _FORECAST_PERIODS:
        for pool, dest, val, desc in _p2p_static:
            rows.append((period, 'Forecast', pool, dest, val, desc))
    return rows


def _pool_to_pool_pct_rows():
    """Compute Driver Percentage Share per source pool and expand to all periods/versions."""
    from collections import defaultdict
    static = [
        ('CP01','CP02',250.0),('CP01','CP03',180.0),('CP01','CP04',120.0),
        ('CP01','CP05',200.0),('CP01','CP06', 80.0),('CP01','CP07',150.0),
        ('CP01','CP08',160.0),('CP01','CP09', 60.0),
        ('CP03','CP01',150.0),('CP03','CP02',200.0),('CP03','CP04',250.0),
        ('CP03','CP05',200.0),
        ('CP04','CP01',100.0),('CP04','CP02',110.0),('CP04','CP03',130.0),
        ('CP04','CP05',160.0),('CP04','CP06', 90.0),('CP04','CP07',100.0),
        ('CP04','CP08',110.0),('CP04','CP09',100.0),
    ]
    totals = defaultdict(float)
    for pool, _, val in static:
        totals[pool] += val
    rows = []
    for period in _BUDGET_PERIODS:
        for pool, dest, val in static:
            pct = round(val / totals[pool] * 100, 4)
            rows.append((period, 'Budget', pool, dest, val, pct))
    for period in _FORECAST_PERIODS:
        for pool, dest, val in static:
            pct = round(val / totals[pool] * 100, 4)
            rows.append((period, 'Forecast', pool, dest, val, pct))
    return rows


# ── Activity to Activity Driver Input ────────────────────────────────────────
# (activity_code, activity_dest_code, driver_value, driver_description)
# Three source activities: A11 (Infection Prevention), A08 (Theatre Scheduling),
# A05 (Diagnostic Ordering). Percentages sum to 100 per source activity.

def _a2a_driver_input_rows():
    _a2a_static = [
        # A11 Infection Prevention → clinical activities by infection risk score
        ('A11','A01', 300.0, 'Infection Risk Score'),
        ('A11','A03', 450.0, 'Infection Risk Score'),
        ('A11','A04', 250.0, 'Infection Risk Score'),
        # A08 Theatre Scheduling → surgical activities by theatre sessions
        ('A08','A02', 600.0, 'Theatre Sessions'),
        ('A08','A03', 400.0, 'Theatre Sessions'),
        # A05 Diagnostic Ordering → diagnostic reporting by order count
        ('A05','A06',1000.0, 'Order Count'),
    ]
    rows = []
    for period in _BUDGET_PERIODS:
        for act, dest, val, desc in _a2a_static:
            rows.append((period, 'Budget', act, dest, val, desc))
    for period in _FORECAST_PERIODS:
        for act, dest, val, desc in _a2a_static:
            rows.append((period, 'Forecast', act, dest, val, desc))
    return rows


def _a2a_driver_pct_rows():
    """Compute Driver Percentage Share for activity-to-activity drivers."""
    from collections import defaultdict
    static = [
        ('A11','A01', 300.0), ('A11','A03', 450.0), ('A11','A04', 250.0),
        ('A08','A02', 600.0), ('A08','A03', 400.0),
        ('A05','A06',1000.0),
    ]
    totals = defaultdict(float)
    for act, _, val in static:
        totals[act] += val
    rows = []
    for period in _BUDGET_PERIODS:
        for act, dest, val in static:
            pct = round(val / totals[act] * 100, 4)
            rows.append((period, 'Budget', act, dest, val, pct))
    for period in _FORECAST_PERIODS:
        for act, dest, val in static:
            pct = round(val / totals[act] * 100, 4)
            rows.append((period, 'Forecast', act, dest, val, pct))
    return rows


# ── Activity Driver Input ─────────────────────────────────────────────────────
# Mirror of activity_drivers, with period/version — feeds CST Activity Driver Input.

def _activity_driver_input_rows():
    rows = []
    for period in _BUDGET_PERIODS:
        for act, sl, val, pct in ACTIVITY_DRIVERS:
            rows.append((period, 'Budget', act, sl, val, 'Activity Driver Value'))
    for period in _FORECAST_PERIODS:
        for act, sl, val, pct in ACTIVITY_DRIVERS:
            rows.append((period, 'Forecast', act, sl, val, 'Activity Driver Value'))
    return rows


# ── Driver Values ─────────────────────────────────────────────────────────────
# (period, version, cost_pool_code, driver_code, driver_value)
# Static across Budget periods.

DRIVER_VALUES_STATIC = [
    # CP01 Facilities
    ('CP01','FLOORSPACE', 12000.0), ('CP01','HEADCOUNT',   45.0),
    # CP02 Clinical Engineering
    ('CP02','FLOORSPACE',   800.0), ('CP02','HEADCOUNT',   12.0),
    ('CP02','ASSETVALUE',  4500.0),
    # CP03 Information Technology
    ('CP03','FLOORSPACE',   600.0), ('CP03','HEADCOUNT',   18.0),
    ('CP03','TRANSACTIONS',250000.0),
    # CP04 Human Resources
    ('CP04','FLOORSPACE',   500.0), ('CP04','HEADCOUNT',    8.0),
    # CP05 Finance and Admin
    ('CP05','FLOORSPACE',   800.0), ('CP05','HEADCOUNT',   15.0),
    ('CP05','TRANSACTIONS', 85000.0),
    # CP06 Sterilisation
    ('CP06','FLOORSPACE',   400.0), ('CP06','HEADCOUNT',   10.0),
    # CP07 Patient Transport
    ('CP07','FLOORSPACE',   300.0), ('CP07','HEADCOUNT',   22.0),
    # CP08 Catering
    ('CP08','FLOORSPACE',  1200.0), ('CP08','HEADCOUNT',   35.0),
    # CP09 Executive and Governance
    ('CP09','FLOORSPACE',   600.0), ('CP09','HEADCOUNT',    6.0),
]


def _driver_value_rows():
    rows = []
    for period in _BUDGET_PERIODS:
        for pool, driver, val in DRIVER_VALUES_STATIC:
            rows.append((period, 'Budget', pool, driver, val))
    for period in _FORECAST_PERIODS:
        for pool, driver, val in DRIVER_VALUES_STATIC:
            rows.append((period, 'Forecast', pool, driver, val))
    return rows


# ── Account Driver ────────────────────────────────────────────────────────────
# (period, version, cost_centre_code, account_code, driver_code)
# Maps each overhead account to its primary cost driver. Static across periods.

ACCOUNT_DRIVER_STATIC = [
    # Facility Management accounts → FLOORSPACE
    ('D013','6001','FLOORSPACE'), ('D013','6003','FLOORSPACE'),
    ('D013','6004','FLOORSPACE'), ('D013','6005','FLOORSPACE'),
    # Clinical Engineering accounts → ASSETVALUE
    ('D014','6006','ASSETVALUE'), ('D014','6007','ASSETVALUE'),
    # Information Technology accounts → TRANSACTIONS
    ('D011','6008','TRANSACTIONS'), ('D011','6009','TRANSACTIONS'),
    ('D011','6010','TRANSACTIONS'),
    # Human Resources accounts → HEADCOUNT
    ('D010','6011','HEADCOUNT'), ('D010','6012','HEADCOUNT'),
    ('D010','6013','HEADCOUNT'),
    # Finance and Administration accounts → TRANSACTIONS
    ('D009','6002','TRANSACTIONS'), ('D009','6014','TRANSACTIONS'),
    ('D009','6015','TRANSACTIONS'), ('D009','6016','TRANSACTIONS'),
    # Sterilisation accounts → HEADCOUNT
    ('D015','6017','HEADCOUNT'), ('D015','6018','HEADCOUNT'),
    # Patient Transport accounts → HEADCOUNT
    ('D016','6019','HEADCOUNT'), ('D016','6020','HEADCOUNT'),
    # Catering accounts → HEADCOUNT
    ('D017','6021','HEADCOUNT'), ('D017','6022','HEADCOUNT'),
    # Executive accounts → HEADCOUNT
    ('D012','6023','HEADCOUNT'), ('D012','6024','HEADCOUNT'),
    ('D012','6025','HEADCOUNT'), ('D012','6026','HEADCOUNT'),
]


def _account_driver_rows():
    rows = []
    for period in _BUDGET_PERIODS:
        for cc, acct, driver in ACCOUNT_DRIVER_STATIC:
            rows.append((period, 'Budget', cc, acct, driver))
    for period in _FORECAST_PERIODS:
        for cc, acct, driver in ACCOUNT_DRIVER_STATIC:
            rows.append((period, 'Forecast', cc, acct, driver))
    return rows


# ── Driver Assumptions ────────────────────────────────────────────────────────
# (period, version, cost_pool_code, pool_to_pool_basis, pool_to_activity_basis,
#  activity_to_sl_basis)
# Driver basis values use CST Driver dimension codes:
#   FLOORSPACE | HEADCOUNT | ASSETVALUE | POWERUSAGE | BEDDAYS | TRANSACTIONS

_DRIVER_ASSUMPTIONS_STATIC = [
    ('Budget','CP01','FLOORSPACE', 'BEDDAYS',       'BEDDAYS'),
    ('Budget','CP02','FLOORSPACE', 'ASSETVALUE',    'TRANSACTIONS'),
    ('Budget','CP03','TRANSACTIONS','TRANSACTIONS', 'TRANSACTIONS'),
    ('Budget','CP04','HEADCOUNT',  'HEADCOUNT',     'HEADCOUNT'),
    ('Budget','CP05','TRANSACTIONS','TRANSACTIONS', 'TRANSACTIONS'),
    ('Budget','CP06','HEADCOUNT',  'TRANSACTIONS',  'TRANSACTIONS'),
    ('Budget','CP07','HEADCOUNT',  'BEDDAYS',       'BEDDAYS'),
    ('Budget','CP08','FLOORSPACE', 'BEDDAYS',       'BEDDAYS'),
    ('Budget','CP09','HEADCOUNT',  'HEADCOUNT',     'HEADCOUNT'),
]

# Activity Driver Assumptions — which driver each Activity uses for A→SL allocation
# (version, activity_code, activity_to_sl_basis)
_ACTIVITY_DRIVER_ASSUMPTIONS_STATIC = [
    ('Budget','A01','BEDDAYS'),
    ('Budget','A02','TRANSACTIONS'),
    ('Budget','A03','BEDDAYS'),
    ('Budget','A04','BEDDAYS'),
    ('Budget','A05','TRANSACTIONS'),
    ('Budget','A06','TRANSACTIONS'),
    ('Budget','A07','HEADCOUNT'),
    ('Budget','A08','TRANSACTIONS'),
    ('Budget','A09','BEDDAYS'),
    ('Budget','A10','Input'),
    ('Budget','A11','HEADCOUNT'),
]

# Activity Driver Values — raw driver volumes per Activity × Driver type
# (activity_code, driver_code, driver_value)
_ACTIVITY_DRIVER_VALUES_STATIC = [
    # BEDDAYS per activity
    ('A01','BEDDAYS',    4500), ('A02','BEDDAYS',    2200), ('A03','BEDDAYS',    3800),
    ('A04','BEDDAYS',    5000), ('A05','BEDDAYS',    1500), ('A06','BEDDAYS',    1800),
    ('A07','BEDDAYS',    2800), ('A08','BEDDAYS',    1600), ('A09','BEDDAYS',    2100),
    ('A10','BEDDAYS',    1200), ('A11','BEDDAYS',    3400),
    # HEADCOUNT per activity
    ('A01','HEADCOUNT',     8), ('A02','HEADCOUNT',    12), ('A03','HEADCOUNT',    15),
    ('A04','HEADCOUNT',    10), ('A05','HEADCOUNT',     6), ('A06','HEADCOUNT',     8),
    ('A07','HEADCOUNT',     9), ('A08','HEADCOUNT',     5), ('A09','HEADCOUNT',     4),
    ('A10','HEADCOUNT',     6), ('A11','HEADCOUNT',     7),
    # TRANSACTIONS per activity
    ('A01','TRANSACTIONS',1200), ('A02','TRANSACTIONS', 850), ('A03','TRANSACTIONS',1600),
    ('A04','TRANSACTIONS', 700), ('A05','TRANSACTIONS',2100), ('A06','TRANSACTIONS',1900),
    ('A07','TRANSACTIONS',1100), ('A08','TRANSACTIONS', 950), ('A09','TRANSACTIONS', 600),
    ('A10','TRANSACTIONS',1800), ('A11','TRANSACTIONS', 450),
    # ASSETVALUE per activity
    ('A01','ASSETVALUE', 250000), ('A02','ASSETVALUE', 480000), ('A03','ASSETVALUE', 620000),
    ('A04','ASSETVALUE', 180000), ('A05','ASSETVALUE', 350000), ('A06','ASSETVALUE', 290000),
    ('A07','ASSETVALUE', 160000), ('A08','ASSETVALUE', 520000), ('A09','ASSETVALUE',  90000),
    ('A10','ASSETVALUE', 130000), ('A11','ASSETVALUE',  75000),
]

_BUDGET_PERIODS = [
    '2025-04', '2025-05', '2025-06', '2025-07', '2025-08', '2025-09',
    '2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03',
]
_FORECAST_PERIODS = [
    '2026-03', '2026-04', '2026-05', '2026-06', '2026-07', '2026-08',
    '2026-09', '2026-10', '2026-11', '2026-12', '2027-01', '2027-02',
    '2027-03', '2027-04', '2027-05', '2027-06', '2027-07', '2027-08',
]
_PERIODS = _BUDGET_PERIODS  # used by assumptions expansion (Budget only)


def _driver_assumptions_rows():
    rows = [(p, v, pool, p2p, p2a, a2sl)
            for v, pool, p2p, p2a, a2sl in _DRIVER_ASSUMPTIONS_STATIC
            for p in _BUDGET_PERIODS]
    rows += [(p, 'Forecast', pool, p2p, p2a, a2sl)
             for _, pool, p2p, p2a, a2sl in _DRIVER_ASSUMPTIONS_STATIC
             for p in _FORECAST_PERIODS]
    return rows


def _activity_driver_assumptions_rows():
    rows = [(p, v, act, basis)
            for v, act, basis in _ACTIVITY_DRIVER_ASSUMPTIONS_STATIC
            for p in _BUDGET_PERIODS]
    rows += [(p, 'Forecast', act, basis)
             for _, act, basis in _ACTIVITY_DRIVER_ASSUMPTIONS_STATIC
             for p in _FORECAST_PERIODS]
    return rows


def _activity_driver_values_rows():
    rows = [(p, 'Budget', act, drv, val)
            for act, drv, val in _ACTIVITY_DRIVER_VALUES_STATIC
            for p in _BUDGET_PERIODS]
    rows += [(p, 'Forecast', act, drv, val)
             for act, drv, val in _ACTIVITY_DRIVER_VALUES_STATIC
             for p in _FORECAST_PERIODS]
    return rows


# ── Apportionment Config rows (expanded to all periods/versions) ──────────────

def _appor_config_rows():
    rows = []
    for period in _BUDGET_PERIODS:
        for acct, cc, pool, pct in APPOR_CONFIG_STATIC:
            rows.append((period, 'Budget', cc, acct, pool, pct))
    for period in _FORECAST_PERIODS:
        for acct, cc, pool, pct in APPOR_CONFIG_STATIC:
            rows.append((period, 'Forecast', cc, acct, pool, pct))
    return rows


# ── DDL ──────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE gl_accounts (
    account_code  TEXT PRIMARY KEY,
    account_desc  TEXT NOT NULL,
    account_type  TEXT NOT NULL,   -- Revenue | Direct Costs | Overhead | Allocated Overhead
    cost_pool     TEXT             -- CST Cost Pool code this account feeds into (NULL if n/a)
);

CREATE TABLE cost_pools (
    pool_code  TEXT PRIMARY KEY,
    pool_desc  TEXT NOT NULL
);

CREATE TABLE activities (
    activity_code  TEXT PRIMARY KEY,
    activity_desc  TEXT NOT NULL
);

CREATE TABLE service_lines (
    service_line_code  TEXT PRIMARY KEY,
    service_line_desc  TEXT NOT NULL
);

CREATE TABLE pool_drivers (
    pool_code              TEXT    NOT NULL,
    activity_code          TEXT    NOT NULL,
    driver_value           REAL    NOT NULL,
    driver_percentage_share REAL   NOT NULL,
    PRIMARY KEY (pool_code, activity_code),
    FOREIGN KEY (pool_code)     REFERENCES cost_pools(pool_code),
    FOREIGN KEY (activity_code) REFERENCES activities(activity_code)
);

CREATE TABLE activity_drivers (
    activity_code           TEXT   NOT NULL,
    service_line_code       TEXT   NOT NULL,
    driver_value            REAL   NOT NULL,
    driver_percentage_share REAL   NOT NULL,
    PRIMARY KEY (activity_code, service_line_code),
    FOREIGN KEY (activity_code)     REFERENCES activities(activity_code),
    FOREIGN KEY (service_line_code) REFERENCES service_lines(service_line_code)
);

CREATE TABLE gl_input (
    period             TEXT  NOT NULL,
    version            TEXT  NOT NULL,
    account_code       TEXT  NOT NULL,
    department_code    TEXT  NOT NULL,
    amount             REAL  NOT NULL,
    PRIMARY KEY (period, version, account_code, department_code),
    FOREIGN KEY (account_code) REFERENCES gl_accounts(account_code)
);

CREATE TABLE apportionment_config (
    period             TEXT  NOT NULL,
    version            TEXT  NOT NULL,
    cost_centre_code   TEXT  NOT NULL,
    account_code       TEXT  NOT NULL,
    cost_pool_code     TEXT  NOT NULL,
    apportionment_pct  REAL  NOT NULL,
    PRIMARY KEY (period, version, cost_centre_code, account_code, cost_pool_code),
    FOREIGN KEY (account_code)   REFERENCES gl_accounts(account_code),
    FOREIGN KEY (cost_pool_code) REFERENCES cost_pools(pool_code)
);

CREATE TABLE pool_to_pool_driver_input (
    period              TEXT  NOT NULL,
    version             TEXT  NOT NULL,
    cost_pool_code      TEXT  NOT NULL,
    cost_pool_dest_code TEXT  NOT NULL,
    driver_value        REAL  NOT NULL,
    driver_description  TEXT  NOT NULL,
    PRIMARY KEY (period, version, cost_pool_code, cost_pool_dest_code),
    FOREIGN KEY (cost_pool_code)      REFERENCES cost_pools(pool_code),
    FOREIGN KEY (cost_pool_dest_code) REFERENCES cost_pools(pool_code)
);

CREATE TABLE pool_to_pool_drivers (
    period                  TEXT  NOT NULL,
    version                 TEXT  NOT NULL,
    cost_pool_code          TEXT  NOT NULL,
    cost_pool_dest_code     TEXT  NOT NULL,
    driver_value            REAL  NOT NULL,
    driver_percentage_share REAL  NOT NULL,
    PRIMARY KEY (period, version, cost_pool_code, cost_pool_dest_code),
    FOREIGN KEY (cost_pool_code)      REFERENCES cost_pools(pool_code),
    FOREIGN KEY (cost_pool_dest_code) REFERENCES cost_pools(pool_code)
);

CREATE TABLE activity_to_activity_driver_input (
    period              TEXT  NOT NULL,
    version             TEXT  NOT NULL,
    activity_code       TEXT  NOT NULL,
    activity_dest_code  TEXT  NOT NULL,
    driver_value        REAL  NOT NULL,
    driver_description  TEXT  NOT NULL,
    PRIMARY KEY (period, version, activity_code, activity_dest_code),
    FOREIGN KEY (activity_code)      REFERENCES activities(activity_code),
    FOREIGN KEY (activity_dest_code) REFERENCES activities(activity_code)
);

CREATE TABLE activity_to_activity_drivers (
    period                  TEXT  NOT NULL,
    version                 TEXT  NOT NULL,
    activity_code           TEXT  NOT NULL,
    activity_dest_code      TEXT  NOT NULL,
    driver_value            REAL  NOT NULL,
    driver_percentage_share REAL  NOT NULL,
    PRIMARY KEY (period, version, activity_code, activity_dest_code),
    FOREIGN KEY (activity_code)      REFERENCES activities(activity_code),
    FOREIGN KEY (activity_dest_code) REFERENCES activities(activity_code)
);

CREATE TABLE activity_driver_input (
    period              TEXT  NOT NULL,
    version             TEXT  NOT NULL,
    activity_code       TEXT  NOT NULL,
    service_line_code   TEXT  NOT NULL,
    driver_value        REAL  NOT NULL,
    driver_description  TEXT  NOT NULL,
    PRIMARY KEY (period, version, activity_code, service_line_code),
    FOREIGN KEY (activity_code)     REFERENCES activities(activity_code),
    FOREIGN KEY (service_line_code) REFERENCES service_lines(service_line_code)
);

CREATE TABLE driver_values (
    period          TEXT  NOT NULL,
    version         TEXT  NOT NULL,
    cost_pool_code  TEXT  NOT NULL,
    driver_code     TEXT  NOT NULL,
    driver_value    REAL  NOT NULL,
    PRIMARY KEY (period, version, cost_pool_code, driver_code),
    FOREIGN KEY (cost_pool_code) REFERENCES cost_pools(pool_code)
);

CREATE TABLE account_driver (
    period             TEXT  NOT NULL,
    version            TEXT  NOT NULL,
    cost_centre_code   TEXT  NOT NULL,
    account_code       TEXT  NOT NULL,
    driver_code        TEXT  NOT NULL,
    PRIMARY KEY (period, version, cost_centre_code, account_code),
    FOREIGN KEY (account_code) REFERENCES gl_accounts(account_code)
);

CREATE TABLE driver_assumptions (
    period                     TEXT  NOT NULL,
    version                    TEXT  NOT NULL,
    cost_pool_code             TEXT  NOT NULL,
    pool_to_pool_basis         TEXT  NOT NULL,
    pool_to_activity_basis     TEXT  NOT NULL,
    activity_to_sl_basis       TEXT  NOT NULL,
    PRIMARY KEY (period, version, cost_pool_code),
    FOREIGN KEY (cost_pool_code) REFERENCES cost_pools(pool_code)
);

CREATE TABLE activity_driver_assumptions (
    period                     TEXT  NOT NULL,
    version                    TEXT  NOT NULL,
    activity_code              TEXT  NOT NULL,
    activity_to_sl_basis       TEXT  NOT NULL,
    PRIMARY KEY (period, version, activity_code),
    FOREIGN KEY (activity_code) REFERENCES activities(activity_code)
);

CREATE TABLE activity_driver_values (
    period          TEXT  NOT NULL,
    version         TEXT  NOT NULL,
    activity_code   TEXT  NOT NULL,
    driver_code     TEXT  NOT NULL,
    driver_value    REAL  NOT NULL,
    PRIMARY KEY (period, version, activity_code, driver_code),
    FOREIGN KEY (activity_code) REFERENCES activities(activity_code)
);
"""


# ── Build ────────────────────────────────────────────────────────────────────

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(DDL)

    conn.executemany('INSERT INTO gl_accounts VALUES (?,?,?,?)',  GL_ACCOUNTS)
    conn.executemany('INSERT INTO cost_pools  VALUES (?,?)',      COST_POOLS)
    conn.executemany('INSERT INTO activities  VALUES (?,?)',      ACTIVITIES)
    conn.executemany('INSERT INTO service_lines VALUES (?,?)',    SERVICE_LINES)
    conn.executemany('INSERT INTO pool_drivers VALUES (?,?,?,?)', POOL_DRIVERS)
    conn.executemany('INSERT INTO activity_drivers VALUES (?,?,?,?)', ACTIVITY_DRIVERS)
    conn.executemany('INSERT INTO gl_input VALUES (?,?,?,?,?)',   _gl_input_rows())
    conn.executemany('INSERT INTO apportionment_config VALUES (?,?,?,?,?,?)', _appor_config_rows())
    conn.executemany('INSERT INTO pool_to_pool_driver_input VALUES (?,?,?,?,?,?)', _pool_to_pool_input_rows())
    conn.executemany('INSERT INTO pool_to_pool_drivers VALUES (?,?,?,?,?,?)',      _pool_to_pool_pct_rows())
    conn.executemany('INSERT INTO activity_to_activity_driver_input VALUES (?,?,?,?,?,?)', _a2a_driver_input_rows())
    conn.executemany('INSERT INTO activity_to_activity_drivers VALUES (?,?,?,?,?,?)',      _a2a_driver_pct_rows())
    conn.executemany('INSERT INTO activity_driver_input VALUES (?,?,?,?,?,?)', _activity_driver_input_rows())
    conn.executemany('INSERT INTO driver_values VALUES (?,?,?,?,?)', _driver_value_rows())
    conn.executemany('INSERT INTO account_driver VALUES (?,?,?,?,?)', _account_driver_rows())
    conn.executemany('INSERT INTO driver_assumptions VALUES (?,?,?,?,?,?)',         _driver_assumptions_rows())
    conn.executemany('INSERT INTO activity_driver_assumptions VALUES (?,?,?,?)',    _activity_driver_assumptions_rows())
    conn.executemany('INSERT INTO activity_driver_values VALUES (?,?,?,?,?)',       _activity_driver_values_rows())

    conn.commit()

    # Verify percentage sums
    print(f"\n{'─'*60}")
    print("  Verifying driver percentage sums...")
    print(f"{'─'*60}")

    pool_sums = conn.execute(
        'SELECT pool_code, ROUND(SUM(driver_percentage_share),2) FROM pool_drivers GROUP BY pool_code'
    ).fetchall()
    for code, total in pool_sums:
        ok = '✓' if total == 100.0 else '✗'
        print(f"  {ok} pool_drivers  {code}: {total}")

    act_sums = conn.execute(
        'SELECT activity_code, ROUND(SUM(driver_percentage_share),2) FROM activity_drivers GROUP BY activity_code'
    ).fetchall()
    for code, total in act_sums:
        ok = '✓' if total == 100.0 else '✗'
        print(f"  {ok} activity_drivers {code}: {total}")

    cfg_acct = conn.execute(
        'SELECT account_code, cost_centre_code, ROUND(SUM(apportionment_pct),2) pct '
        'FROM apportionment_config '
        'WHERE period="2025-07" GROUP BY account_code, cost_centre_code '
        'ORDER BY account_code, cost_centre_code'
    ).fetchall()
    for code, cc, total in cfg_acct:
        ok = '✓' if total == 100.0 else '✗'
        print(f"  {ok} apportionment_config {code} / {cc}: {total}%")

    counts = {
        tbl: conn.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
        for tbl in ['gl_accounts','cost_pools','activities','service_lines',
                    'pool_drivers','activity_drivers','gl_input',
                    'apportionment_config','pool_to_pool_driver_input',
                    'pool_to_pool_drivers','activity_to_activity_driver_input',
                    'activity_to_activity_drivers','activity_driver_input',
                    'driver_values','account_driver','driver_assumptions',
                    'activity_driver_assumptions','activity_driver_values']
    }

    conn.close()

    print(f"\n{'─'*60}")
    print(f"  Written: {DB_PATH}")
    print(f"{'─'*60}")
    for tbl, n in counts.items():
        print(f"  {tbl:<42} {n:>6} rows")
    print()


if __name__ == '__main__':
    main()
