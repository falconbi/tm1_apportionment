"""
create_cst_subsets_and_views.py
Creates one default MDX view per CST cube named 'RPT Default'.
Called by build_cst_model.py.

Standard apportionment view pattern:
  WHERE  : Version=Budget, Period=Apr FY2025, Measure=Apportioned Amount
  COLUMNS: NON EMPTY CROSSJOIN(GBL Cost Centre leaves, primary dest dimension leaves)
  ROWS   : NON EMPTY source dimension leaves
"""

import sys
sys.path.insert(0, '.')
from TM1py.Objects import MDXView
from tm1py_connect import get_tm1_service
from gbl_check import verify_gbl


VIEW_NAME = 'RPT Default'


def create_mdx_view(tm1, cube_name, mdx):
    view = MDXView(cube_name, VIEW_NAME, mdx)
    if tm1.views.exists(cube_name, VIEW_NAME, private=False):
        tm1.views.delete(cube_name, VIEW_NAME, private=False)
    tm1.views.create(view, private=False)
    print(f"  ✓ {cube_name} — {VIEW_NAME}")


_WHERE_STD = "[GBL Version].[Budget], [GBL Period].[Apr FY2025]"
_CC = "TM1FILTERBYLEVEL({TM1SUBSETALL([GBL Cost Centre])}, 0)"


def _leaf(dim):
    return f"TM1FILTERBYLEVEL({{TM1SUBSETALL([{dim}])}}, 0)"


def _apportionment_mdx(cube, source_dim, dest_dim, measure_dim, measure_elem,
                       extra_where=''):
    """Build the standard apportionment view MDX.

    Columns : NON EMPTY CROSSJOIN(Cost Centre leaves, dest_dim leaves)
    Rows    : NON EMPTY source_dim leaves
    WHERE   : Version=Budget, Period=Apr FY2025, Measure=measure_elem
              + any extra_where members
    """
    where_parts = [_WHERE_STD, f"[{measure_dim}].[{measure_elem}]"]
    if extra_where:
        where_parts.append(extra_where)
    where = ', '.join(where_parts)
    return f"""SELECT
NON EMPTY CROSSJOIN({_CC}, {_leaf(dest_dim)}) ON COLUMNS,
NON EMPTY {_leaf(source_dim)} ON ROWS
FROM [{cube}]
WHERE ({where})""".strip()


def main(tm1):
    print(f"\n{'─'*60}")
    print("  Creating CST subsets and views...")
    print(f"{'─'*60}")

    # ── GL Input ─────────────────────────────────────────────
    # Columns: Cost Centre   Rows: Account   WHERE: Version, Period, Measure
    create_mdx_view(tm1, 'CST GL Input', f"""
SELECT
NON EMPTY {_CC} ON COLUMNS,
NON EMPTY {_leaf('GBL Account')} ON ROWS
FROM [CST GL Input]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025],
       [CST GL Input Measure].[Amount])""".strip())

    # ── Apportionment Config ──────────────────────────────────
    # Columns: Cost Pool   Rows: Account   WHERE: Version, Period, CostCentre, Measure
    create_mdx_view(tm1, 'CST Apportionment Config', """
SELECT
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([CST Cost Pool])}, 0) ON COLUMNS,
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([GBL Account])}, 0) ON ROWS
FROM [CST Apportionment Config]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025],
       [GBL Cost Centre].[D013],
       [CST Apportionment Config Measure].[Apportionment Pct])""".strip())

    # ── Stage 1: Cost Pool Apportionment ─────────────────────
    # Standard: Cost Centre × Cost Pool | Account
    create_mdx_view(tm1, 'CST Cost Pool Apportionment',
        _apportionment_mdx('CST Cost Pool Apportionment',
                           source_dim='GBL Account',
                           dest_dim='CST Cost Pool',
                           measure_dim='CST Cost Pool Apportionment Measure',
                           measure_elem='Apportioned Amount'))

    # ── Stage 1b: Pool to Pool Apportionment ─────────────────
    # Standard: Cost Centre × Cost Pool Dest | Cost Pool (source)
    create_mdx_view(tm1, 'CST Pool to Pool Apportionment',
        _apportionment_mdx('CST Pool to Pool Apportionment',
                           source_dim='CST Cost Pool',
                           dest_dim='CST Cost Pool Dest',
                           measure_dim='CST Pool to Pool Apportionment Measure',
                           measure_elem='Apportioned Amount'))

    # ── Stage 1b driver ──────────────────────────────────────
    create_mdx_view(tm1, 'CST Pool to Pool Driver', """
SELECT
NON EMPTY {[CST Pool to Pool Driver Measure].[Driver Value],
           [CST Pool to Pool Driver Measure].[Driver Percentage Share]} ON COLUMNS,
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([CST Cost Pool])}, 0) ON ROWS
FROM [CST Pool to Pool Driver]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025],
       [CST Cost Pool Dest].[CP02])""".strip())

    # ── Stage 2: Activity Apportionment ──────────────────────
    # Standard: Cost Centre × Cost Pool | Activity
    create_mdx_view(tm1, 'CST Activity Apportionment',
        _apportionment_mdx('CST Activity Apportionment',
                           source_dim='CST Activity',
                           dest_dim='CST Cost Pool',
                           measure_dim='CST Activity Apportionment Measure',
                           measure_elem='Apportioned Amount'))

    # ── Stage 2 driver ───────────────────────────────────────
    create_mdx_view(tm1, 'CST Pool Driver', """
SELECT
NON EMPTY {[CST Pool Driver Measure].[Driver Value],
           [CST Pool Driver Measure].[Driver Percentage Share]} ON COLUMNS,
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([CST Activity])}, 0) ON ROWS
FROM [CST Pool Driver]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025],
       [CST Cost Pool].[CP01])""".strip())

    # ── Stage 2b: Activity to Activity Apportionment ─────────
    # Standard: Cost Centre × Activity Dest | Activity (source)
    create_mdx_view(tm1, 'CST Activity to Activity Apportionment',
        _apportionment_mdx('CST Activity to Activity Apportionment',
                           source_dim='CST Activity',
                           dest_dim='CST Activity Dest',
                           measure_dim='CST Activity to Activity Apportionment Measure',
                           measure_elem='Apportioned Amount'))

    # ── Stage 2b driver ──────────────────────────────────────
    create_mdx_view(tm1, 'CST Activity to Activity Driver', """
SELECT
NON EMPTY {[CST Activity to Activity Driver Measure].[Driver Value],
           [CST Activity to Activity Driver Measure].[Driver Percentage Share]} ON COLUMNS,
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([CST Activity])}, 0) ON ROWS
FROM [CST Activity to Activity Driver]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025],
       [CST Activity Dest].[A01])""".strip())

    # ── Stage 3: Service Line Cost ────────────────────────────
    # Standard: Cost Centre × Activity | Service Line
    create_mdx_view(tm1, 'CST Service Line Cost',
        _apportionment_mdx('CST Service Line Cost',
                           source_dim='CST Service Line',
                           dest_dim='CST Activity',
                           measure_dim='CST Service Line Cost Measure',
                           measure_elem='Apportioned Amount'))

    # ── Stage 3 driver ───────────────────────────────────────
    create_mdx_view(tm1, 'CST Activity Driver', """
SELECT
NON EMPTY {[CST Activity Driver Measure].[Driver Value],
           [CST Activity Driver Measure].[Driver Percentage Share]} ON COLUMNS,
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([CST Activity])}, 0) ON ROWS
FROM [CST Activity Driver]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025],
       [CST Service Line].[SL01])""".strip())

    # ── P&L Report ────────────────────────────────────────────
    create_mdx_view(tm1, 'CST Profit and Loss Report', """
SELECT
NON EMPTY CROSSJOIN(
  TM1FILTERBYLEVEL({TM1SUBSETALL([CST Service Line])}, 0),
  TM1FILTERBYLEVEL({TM1SUBSETALL([GBL Cost Centre])}, 0)
) ON COLUMNS,
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([GBL Account])}, 0) ON ROWS
FROM [CST Profit and Loss Report]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025],
       [CST Apportionment Stage].[Post Apportionment],
       [CST Profit and Loss Report Measure].[Amount])""".strip())

    # ── Reconciliation ────────────────────────────────────────
    create_mdx_view(tm1, 'CST Apportionment Reconciliation', """
SELECT
NON EMPTY {[CST Apportionment Reconciliation Measure].[Input Total],
           [CST Apportionment Reconciliation Measure].[Output Total],
           [CST Apportionment Reconciliation Measure].[Variance]} ON COLUMNS,
NON EMPTY TM1FILTERBYLEVEL({TM1SUBSETALL([CST Reconciliation Check])}, 0) ON ROWS
FROM [CST Apportionment Reconciliation]
WHERE ([GBL Version].[Budget],
       [GBL Period].[Apr FY2025])""".strip())

    create_driver_views(tm1)
    print(f"  ✓ All CST views created.")


def create_driver_views(tm1):
    """Creates RPT Default views for the six CST Driver layer cubes."""

    # CST Driver Values
    create_mdx_view(tm1, 'CST Driver Values', """
SELECT
  {[CST Driver Values Measure].[Driver Value]} ON COLUMNS,
  TM1FILTERBYLEVEL({TM1SUBSETALL([CST Driver])},0) ON ROWS
FROM [CST Driver Values]
WHERE ([CST Cost Pool].[CP01],
       [GBL Period].[Jul FY2025],
       [GBL Version].[Budget])
""".strip())

    # CST Account Driver
    create_mdx_view(tm1, 'CST Account Driver', """
SELECT
  {[CST Account Driver Measure].[Driver Code]} ON COLUMNS,
  TM1FILTERBYLEVEL({TM1SUBSETALL([GBL Account])},0) ON ROWS
FROM [CST Account Driver]
WHERE ([GBL Cost Centre].[D013],
       [GBL Period].[Jul FY2025],
       [GBL Version].[Budget])
""".strip())

    # CST Pool to Pool Driver Input
    create_mdx_view(tm1, 'CST Pool to Pool Driver Input', """
SELECT
  {[CST Pool to Pool Driver Input Measure].[Driver Value],
   [CST Pool to Pool Driver Input Measure].[Driver Description]} ON COLUMNS,
  TM1FILTERBYLEVEL({TM1SUBSETALL([CST Cost Pool])},0) ON ROWS
FROM [CST Pool to Pool Driver Input]
WHERE ([CST Cost Pool Dest].[CP02],
       [GBL Period].[Jul FY2025],
       [GBL Version].[Budget])
""".strip())

    # CST Activity to Activity Driver Input
    create_mdx_view(tm1, 'CST Activity to Activity Driver Input', """
SELECT
  {[CST Activity to Activity Driver Input Measure].[Driver Value],
   [CST Activity to Activity Driver Input Measure].[Driver Description]} ON COLUMNS,
  TM1FILTERBYLEVEL({TM1SUBSETALL([CST Activity])},0) ON ROWS
FROM [CST Activity to Activity Driver Input]
WHERE ([CST Activity Dest].[A01],
       [GBL Period].[Jul FY2025],
       [GBL Version].[Budget])
""".strip())

    # CST Activity Driver Input
    create_mdx_view(tm1, 'CST Activity Driver Input', """
SELECT
  {[CST Activity Driver Input Measure].[Driver Value],
   [CST Activity Driver Input Measure].[Driver Description]} ON COLUMNS,
  TM1FILTERBYLEVEL({TM1SUBSETALL([CST Activity])},0) ON ROWS
FROM [CST Activity Driver Input]
WHERE ([CST Service Line].[SL01],
       [GBL Period].[Jul FY2025],
       [GBL Version].[Budget])
""".strip())

    # CST Driver Assumptions
    create_mdx_view(tm1, 'CST Driver Assumptions', """
SELECT
  {[CST Driver Assumptions Measure].[Pool to Pool Basis],
   [CST Driver Assumptions Measure].[Pool to Activity Basis],
   [CST Driver Assumptions Measure].[Activity to Service Line Basis]} ON COLUMNS,
  TM1FILTERBYLEVEL({TM1SUBSETALL([CST Cost Pool])},0) ON ROWS
FROM [CST Driver Assumptions]
WHERE ([GBL Version].[Budget])
""".strip())


if __name__ == '__main__':
    tm1 = get_tm1_service()
    verify_gbl(tm1)
    main(tm1)
    tm1.logout()
