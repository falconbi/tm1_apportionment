"""
etl/poller.py
Polls CST ETL Control cube for REQUESTED jobs and dispatches to the
appropriate ETL script.  Runs as a long-lived process on the TM1py server.

Usage:
    python3 etl/poller.py                 # poll every 30 seconds
    python3 etl/poller.py --interval 60   # poll every 60 seconds

Systemd:
    See deploy/cst-poller.service
"""

import argparse
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tm1py_connect import get_tm1_service
import etl.load_gl as load_gl
import etl.load_drivers as load_drivers
import etl.run_apportionment as run_apportionment

CONTROL_CUBE = 'CST ETL Control'
CONTROL_DIMS = ['CST ETL Job', 'CST ETL Control Measure']

DISPATCHER = {
    'Load GL':           load_gl.main,
    'Load Drivers':      load_drivers.main,
    'Run Apportionment': run_apportionment.main,
}


def _now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')


def _read_job(tm1, job):
    """Read all control measures for a job in one call."""
    measures = ['Status', 'Period', 'Version', 'Force', 'Max Iter']
    result = {}
    for m in measures:
        result[m] = tm1.cells.get_value(
            CONTROL_CUBE, f'{job},{m}', dimensions=CONTROL_DIMS
        )
    return result


def _write(tm1, job, cells):
    """Write measure values for a job."""
    tm1.cells.write_values(
        CONTROL_CUBE,
        {(job, m): v for m, v in cells.items()},
        dimensions=CONTROL_DIMS,
    )


def _dispatch(tm1, job, params):
    """Run the ETL function for a job, return (status, message)."""
    fn = DISPATCHER[job]
    period  = params.get('Period') or None
    version = params.get('Version') or 'Budget'

    try:
        if job == 'Run Apportionment':
            max_iter = int(params.get('Max Iter') or 100)
            force    = bool(params.get('Force') or False)
            fn(period=period, version=version, max_iter=max_iter, force=force)
        else:
            fn(period=period, version=version)

        label = period or f'all {version} periods'
        return 'COMPLETE', f'Completed for {label}'

    except SystemExit:
        # run_apportionment exits 1 on RC failures
        return 'FAILED', 'RC checks failed — review in PAW'
    except Exception:
        return 'FAILED', traceback.format_exc().splitlines()[-1]


def poll_once(tm1):
    """Check all jobs — process any that are REQUESTED."""
    for job in DISPATCHER:
        params = _read_job(tm1, job)
        if (params.get('Status') or '').strip() != 'REQUESTED':
            continue

        print(f"  → {job} REQUESTED — starting")
        _write(tm1, job, {'Status': 'RUNNING', 'Requested At': _now()})

        status, message = _dispatch(tm1, job, params)

        _write(tm1, job, {
            'Status':       status,
            'Message':      message,
            'Completed At': _now(),
        })
        icon = '✓' if status == 'COMPLETE' else '✗'
        print(f"  {icon} {job} {status} — {message}")


def main(interval=30):
    print(f"\n  CST ETL Poller started — polling every {interval}s")
    print(f"  Jobs: {', '.join(DISPATCHER)}\n")

    while True:
        try:
            with get_tm1_service() as tm1:
                poll_once(tm1)
        except Exception:
            print(f"  ! Poller error: {traceback.format_exc().splitlines()[-1]}")

        time.sleep(interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', type=int, default=30,
                        help='Poll interval in seconds (default 30)')
    args = parser.parse_args()
    main(args.interval)
