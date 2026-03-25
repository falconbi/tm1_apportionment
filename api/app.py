"""
api/app.py
Lightweight Flask API that exposes CST ETL scripts as HTTP endpoints.
Called by TM1 TI processes via HTTPRequest in PA v12 (no ExecuteCommand).

Endpoints:
  POST /gl/load           — load_gl.main()
  POST /drivers/load      — load_drivers.main()
  POST /apportionment/run — run_apportionment.main()

All endpoints accept JSON body:
  { "period": "2025-04", "version": "Budget" }          # GL / Drivers
  { "period": "2025-04", "version": "Budget",
    "max_iter": 100, "force": false }                    # Apportionment

period is optional — omit to run all periods for the version.

Usage:
  python3 api/app.py                   # default port 5000
  python3 api/app.py --port 8080
"""

import argparse
import sys
import traceback
from pathlib import Path

from flask import Flask, jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import etl.load_gl as load_gl
import etl.load_drivers as load_drivers
import etl.run_apportionment as run_apportionment

app = Flask(__name__)


def _parse_body():
    body    = request.get_json(silent=True) or {}
    period  = body.get('period') or None
    version = body.get('version', 'Budget')
    return period, version, body


def _ok(message):
    return jsonify({'status': 'ok', 'message': message}), 200


def _err(message, code=500):
    return jsonify({'status': 'error', 'message': message}), code


# ── GL ───────────────────────────────────────────────────────────────────────

@app.route('/gl/load', methods=['POST'])
def gl_load():
    period, version, _ = _parse_body()
    try:
        load_gl.main(period=period, version=version)
        label = period or f'all {version} periods'
        return _ok(f'GL loaded for {label}')
    except Exception:
        return _err(traceback.format_exc())


# ── Drivers ──────────────────────────────────────────────────────────────────

@app.route('/drivers/load', methods=['POST'])
def drivers_load():
    period, version, _ = _parse_body()
    try:
        load_drivers.main(period=period, version=version)
        label = period or f'all {version} periods'
        return _ok(f'Drivers loaded for {label}')
    except Exception:
        return _err(traceback.format_exc())


# ── Apportionment ─────────────────────────────────────────────────────────────

@app.route('/apportionment/run', methods=['POST'])
def apportionment_run():
    period, version, body = _parse_body()
    max_iter = int(body.get('max_iter', 100))
    force    = bool(body.get('force', False))
    try:
        run_apportionment.main(period=period, version=version,
                               max_iter=max_iter, force=force)
        label = period or f'all {version} periods'
        return _ok(f'Apportionment complete for {label}')
    except SystemExit as e:
        # run_apportionment calls sys.exit(1) on RC failures
        return _err(f'Apportionment completed with RC failures — review in PAW', code=422)
    except Exception:
        return _err(traceback.format_exc())


# ── Health ────────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return _ok('CST Apportionment API running')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()
    app.run(host=args.host, port=args.port)
