"""
etl/utils.py
Shared helpers for ETL scripts.
"""


def get_version_periods(tm1, version):
    """Return ordered list of period strings for a version, driven by
    Start Period and End Period element attributes on GBL Version.

    Returns e.g. ['2025-04', '2025-05', ..., '2026-03']
    """
    attrs = tm1.elements.get_attribute_of_elements(
        dimension_name='GBL Version',
        hierarchy_name='GBL Version',
        attribute='Start Period',
        elements=[version],
    )
    start = attrs.get(version)

    attrs = tm1.elements.get_attribute_of_elements(
        dimension_name='GBL Version',
        hierarchy_name='GBL Version',
        attribute='End Period',
        elements=[version],
    )
    end = attrs.get(version)

    if not start or not end:
        raise ValueError(
            f"GBL Version '{version}' is missing Start Period or End Period attributes"
        )

    return _period_range(start, end)


def _period_range(start, end):
    """Generate YYYY-MM strings from start to end inclusive."""
    periods = []
    current = start
    while current <= end:
        periods.append(current)
        current = _next_period(current)
    return periods


def _next_period(period):
    year, month = int(period[:4]), int(period[5:7])
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"
