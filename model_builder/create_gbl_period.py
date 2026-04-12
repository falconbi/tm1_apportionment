"""
create_gbl_period.py
Builds the GBL Period dimension using TM1py.

Conventions:
  Element names : YYYY-MM  (calendar month)   2025-04 = April 2025
  FY label      : FY<end-year>                FY2026  = Apr 2025 - Mar 2026
  FY start      : April (FY_START_MONTH)

Hierarchy:
  FY2026
    └── 2025-04, 2025-05, ..., 2026-03
  FY2027
    └── 2026-04, 2026-05, ..., 2027-03

Attributes per leaf element:
  Caption              Apr-25
  Long Name            April 2025
  Next Period          2025-05
  Previous Period      2025-03
  First Period         2025-04  (first element of this FY)
  Last Period          2026-03  (last element of this FY)
  Fin Year             FY2026
  Calendar Month       4
  Calendar Year        2025
  Days in Period       30
  Period Start Serial  <TM1/Excel serial>
  Period End Serial    <TM1/Excel serial>
"""

import calendar
import sys
from datetime import date

sys.path.insert(0, '.')
from TM1py.Objects import Dimension, Hierarchy
from tm1py_connect import get_tm1_service

# ── Configuration ──────────────────────────────────────────────────────────────
DIMENSION_NAME = 'GBL Period'
START_YEAR     = 2023   # first calendar year
END_YEAR       = 2030   # last calendar year
FY_START_MONTH = 4      # April — change to 7 for July FY, 1 for calendar year


# ── Helpers ────────────────────────────────────────────────────────────────────

def _excel_serial(d: date) -> int:
    """TM1/Excel serial — days since 1899-12-30."""
    return (d - date(1899, 12, 30)).days


def _fy_end_year(year: int, month: int) -> int:
    """FY end-year for a calendar month. Works for any non-January FY start."""
    return year + 1 if month >= FY_START_MONTH else year


def _fy_bounds(fy_end: int) -> tuple:
    """Return (first_elem, last_elem) for a FY given its end year."""
    end_month  = (FY_START_MONTH - 1) or 12
    start_year = fy_end - 1
    end_year   = fy_end if end_month < FY_START_MONTH else fy_end - 1
    return f'{start_year}-{FY_START_MONTH:02d}', f'{end_year}-{end_month:02d}'


# ── Build ──────────────────────────────────────────────────────────────────────

def main(tm1):
    print(f"\n  Building {DIMENSION_NAME}...")

    hier = Hierarchy(name=DIMENSION_NAME, dimension_name=DIMENSION_NAME)

    for attr in ('Caption', 'Long Name', 'Next Period', 'Previous Period',
                 'First Period', 'Last Period', 'Fin Year'):
        hier.add_element_attribute(attr, 'String')

    for attr in ('Calendar Month', 'Calendar Year', 'Days in Period',
                 'Period Start Serial', 'Period End Serial'):
        hier.add_element_attribute(attr, 'Numeric')

    # FY consolidations
    fy_end_years = sorted({
        _fy_end_year(yr, mo)
        for yr in range(START_YEAR, END_YEAR + 1)
        for mo in range(1, 13)
    })
    for fy_end in fy_end_years:
        hier.add_element(f'FY{fy_end}', 'Consolidated')

    # Leaf elements — calendar month YYYY-MM
    for yr in range(START_YEAR, END_YEAR + 1):
        for mo in range(1, 13):
            elem   = f'{yr}-{mo:02d}'
            fy_end = _fy_end_year(yr, mo)
            hier.add_element(elem, 'Numeric')
            hier.add_edge(f'FY{fy_end}', elem, 1)

    dim = Dimension(DIMENSION_NAME, [hier])
    tm1.dimensions.update_or_create(dim)

    # ── Attribute values ───────────────────────────────────────────────────────
    MONTH_ABBR = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    attr_cube = f'}}ElementAttributes_{DIMENSION_NAME}'
    attr_dims = [DIMENSION_NAME, f'}}ElementAttributes_{DIMENSION_NAME}']
    cells = {}

    for yr in range(START_YEAR, END_YEAR + 1):
        for mo in range(1, 13):
            elem            = f'{yr}-{mo:02d}'
            fy_end          = _fy_end_year(yr, mo)
            first, last     = _fy_bounds(fy_end)
            days            = calendar.monthrange(yr, mo)[1]
            next_p          = f'{yr + 1}-01'     if mo == 12 else f'{yr}-{mo + 1:02d}'
            prev_p          = f'{yr - 1}-12'     if mo == 1  else f'{yr}-{mo - 1:02d}'

            cells[(elem, 'Caption')]             = f'{MONTH_ABBR[mo]}-{str(yr)[2:]}'
            cells[(elem, 'Long Name')]           = f'{calendar.month_name[mo]} {yr}'
            cells[(elem, 'Next Period')]         = next_p
            cells[(elem, 'Previous Period')]     = prev_p
            cells[(elem, 'First Period')]        = first
            cells[(elem, 'Last Period')]         = last
            cells[(elem, 'Fin Year')]            = f'FY{fy_end}'
            cells[(elem, 'Calendar Month')]      = mo
            cells[(elem, 'Calendar Year')]       = yr
            cells[(elem, 'Days in Period')]      = days
            cells[(elem, 'Period Start Serial')] = _excel_serial(date(yr, mo, 1))
            cells[(elem, 'Period End Serial')]   = _excel_serial(date(yr, mo, days))

    tm1.cells.write_values(attr_cube, cells, dimensions=attr_dims)

    leaf_count = (END_YEAR - START_YEAR + 1) * 12
    print(f"  ✓ {DIMENSION_NAME} — {len(fy_end_years)} FY consolidations, {leaf_count} leaves")
    print(f"    Range : {START_YEAR}-01 → {END_YEAR}-12")
    print(f"    FY    : FY{min(fy_end_years)} → FY{max(fy_end_years)}")
    print(f"    Start : month {FY_START_MONTH} ({MONTH_ABBR[FY_START_MONTH]}), end-year labelling")


if __name__ == '__main__':
    with get_tm1_service() as tm1:
        main(tm1)
