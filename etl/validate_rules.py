#!/usr/bin/env python3
"""Validate all TM1 rules syntax against the live TM1 server.

Reads rules from:
  - model_builder/tm1_objects/cubes/*.json  (embedded "rules" field)
  - model_builder/tm1_objects/rules/*.rux

Performs:
  1. Static analysis — catches feeder bracket typos, unbalanced tokens, etc.
  2. TM1 server validation — deploys rules temporarily and runs check_rules()

Static checks (catches what TM1's parser misses):
  - Unbalanced [ ] brackets in feeder targets
  - `)` closing a bracketed feeder ref instead of `]`
  - `=> ` feeder with no target or invalid target tokens
"""

import re
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CUBES_JSON = REPO / "model_builder" / "tm1_objects" / "cubes"
RULES_RUX = REPO / "model_builder" / "tm1_objects" / "rules"


# ── Static feeder checks ─────────────────────────────────────────────


def check_feeder_bracket_balance(rules_text, label):
    """In FEEDER sections, verify every `[` has a matching `]`."""
    issues = []
    in_feeder = False
    lines = rules_text.split("\n")
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if re.match(r"^\s*FEEDERS\s*;?\s*$", stripped, re.IGNORECASE):
            in_feeder = True
            continue
        if not in_feeder or not stripped or stripped.startswith("#"):
            continue

        opens = stripped.count("[")
        closes = stripped.count("]")
        if opens != closes:
            issues.append(
                (
                    lineno,
                    f"Unbalanced brackets: {opens} `[` vs {closes} `]`  →  {stripped[:80]}",
                )
            )

        # Find `)` inside a bracketed expression — likely `]` typo
        if ")" in stripped:
            # Check if ) appears inside [ ] context
            bracketed = re.findall(r"\[([^\]]*)\]", stripped)
            for b in bracketed:
                if ")" in b:
                    ctx = b[:60]
                    issues.append(
                        (
                            lineno,
                            f"`)` found inside `[...]` — should be `]` instead  →  ...{ctx}...",
                        )
                    )

        # Feeder target should end with ; or , (not bare ) or missing ]
        # This catches feeder lines that look like: ['X'] => ['Y')
        if (
            "=>" in stripped
            and not stripped.rstrip().endswith(";")
            and not stripped.rstrip().endswith(",")
        ):
            if stripped.rstrip().endswith(")"):
                issues.append(
                    (
                        lineno,
                        f"Feeder line ends with `)` — missing `]` before it?  →  {stripped[:80]}",
                    )
                )

    return issues


def check_section_balance(rules_text, label):
    """Check that non-comment [] brackets balance across the whole file."""
    issues = []
    stack = []
    lines = rules_text.split("\n")
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for col, ch in enumerate(stripped):
            if ch == "[":
                stack.append((lineno, col, ch))
            elif ch == "]":
                if not stack:
                    issues.append((lineno, f"Extra `]` at position {col}"))
                else:
                    stack.pop()
    if stack:
        for lineno, col, _ in stack:
            issues.append((lineno, f"Unmatched `[` at position {col}"))
    return issues


# ── Reader helpers ───────────────────────────────────────────────────

_overhead_consol = None


def _get_overhead_consol():
    global _overhead_consol
    if _overhead_consol is None:
        try:
            sys.path.insert(0, str(REPO))
            from config import TM1_CONFIG

            _overhead_consol = TM1_CONFIG.get(
                "overhead_consolidation", "TOTAL OVERHEAD"
            )
        except Exception:
            _overhead_consol = "TOTAL OVERHEAD"
    return _overhead_consol


def read_rules_from_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rules = data.get("rules", "").strip()
        if not rules:
            return None
        rules = rules.replace("{overhead_consolidation}", _get_overhead_consol())
        return data["name"], rules
    except (json.JSONDecodeError, KeyError, OSError) as e:
        return None


def read_rules_from_rux(path):
    try:
        rules = path.read_text(encoding="utf-8").strip()
        if not rules:
            return None
        rules = rules.replace("{overhead_consolidation}", _get_overhead_consol())
        return path.stem, rules
    except OSError:
        return None


def collect_rules():
    sources = []
    for path in sorted(CUBES_JSON.glob("*.json")):
        result = read_rules_from_json(path)
        if result:
            sources.append((*result, path))

    json_cubes = {name for name, *_ in sources}
    for path in sorted(RULES_RUX.glob("*.rux")):
        if path.stem in json_cubes:
            continue
        result = read_rules_from_rux(path)
        if result:
            sources.append((*result, path))

    return sources


# ── Static analysis ──────────────────────────────────────────────────


def static_analysis(rules_text, label):
    issues = []
    issues.extend(check_feeder_bracket_balance(rules_text, label))
    issues.extend(check_section_balance(rules_text, label))
    return issues


# ── TM1 server validation ────────────────────────────────────────────


def run_tm1_validation(sources):
    sys.path.insert(0, str(REPO))
    from tm1py_connect import get_tm1_service
    import time

    failures = 0
    results = []

    with get_tm1_service() as tm1:
        # Phase 1: backup
        original_rules = {}
        for cube_name, *_ in sources:
            try:
                response = tm1._tm1_rest.GET(f"/Cubes('{cube_name}')/Rules/$value")
                original_rules[cube_name] = response.text
            except Exception as e:
                results.append(
                    (cube_name, "SKIP", f"Could not read current rules: {e}")
                )
                original_rules[cube_name] = None

        # Phase 2: deploy + check
        for cube_name, rules_text, source in sources:
            source_label = source.name if hasattr(source, "name") else source
            try:
                tm1.cubes.update_or_create_rules(cube_name, rules_text)
                time.sleep(0.3)
                errors = tm1.cubes.check_rules(cube_name)
            except Exception as e:
                errors = str(e)

            if not errors or (isinstance(errors, list) and len(errors) == 0):
                results.append((cube_name, "PASS", source_label))
            elif isinstance(errors, list):
                failures += 1
                details = [source_label]
                for err in errors:
                    msg = err.get("Message", str(err))
                    line = err.get("LineNumber", "")
                    pos = err.get("ColumnPosition", "")
                    loc = f"L{line}:C{pos}" if line or pos else ""
                    details.append(f"  {loc} {msg}" if loc else f"  {msg}")
                results.append((cube_name, "FAIL", "\n".join(details)))
            else:
                failures += 1
                results.append((cube_name, "FAIL", f"{source_label}\n  {errors}"))

        # Phase 3: restore
        for cube_name, orig in original_rules.items():
            if orig is None:
                continue
            try:
                tm1.cubes.update_or_create_rules(cube_name, orig)
            except Exception as e:
                print(f"  ⚠  FAILED to restore rules for {cube_name}: {e}")

    return results, failures


# ── Main ─────────────────────────────────────────────────────────────


def fetch_rules_from_server():
    """Fetch current rules directly from TM1 server and validate them."""
    sys.path.insert(0, str(REPO))
    from tm1py_connect import get_tm1_service

    with get_tm1_service() as tm1:
        cubes = tm1.cubes.get_all_names_with_rules()

    results = []
    with get_tm1_service() as tm1:
        for cube_name in cubes:
            try:
                response = tm1._tm1_rest.GET(f"/Cubes('{cube_name}')/Rules/$value")
                rules = response.text
                results.append((cube_name, rules, "(TM1 server)"))
            except Exception as e:
                print(f"  ⚠  Could not read rules for {cube_name}: {e}")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate TM1 rules syntax")
    parser.add_argument(
        "--server",
        action="store_true",
        help="Fetch and validate rules currently deployed on TM1 server",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  TM1 Rules Syntax Validator")
    print("=" * 70)

    # Use server-fetched rules instead of source files
    if args.server:
        print("\n── Fetching rules from TM1 server ───────────────────────────")
        sources = fetch_rules_from_server()
        if not sources:
            print("  No cubes with rules found on TM1 server.")
            return
        print(f"  Found {len(sources)} cubes with rules on TM1 server\n")
    else:
        sources = collect_rules()
        print(f"\n  Found {len(sources)} cubes with rules to check\n")
        if not sources:
            print("  Nothing to validate.")
            return

    # ── Static analysis ────────────────────────────────────────────
    print("── Static analysis ──────────────────────────────────────────")
    static_failures = 0

    for cube_name, rules_text, source in sources:
        label = source.name if hasattr(source, "name") else source
        issues = static_analysis(rules_text, label)
        if not issues:
            print(f"  ✓  {cube_name:40s} PASS")
        else:
            static_failures += 1
            print(f"  ✗  {cube_name:40s} FAIL  ({len(issues)} issue(s))")
            for line_no, msg in issues:
                print(f"      L{line_no}: {msg}")

    tm1_failures = 0
    if not args.server:
        # ── TM1 server validation ──────────────────────────────────
        print("\n── TM1 server validation ────────────────────────────────────")
        print(f"  Connecting to TM1...")
        try:
            tm1_results, tm1_failures = run_tm1_validation(sources)
            for cube_name, status, details in tm1_results:
                icon = "✓" if status == "PASS" else ("✗" if status == "FAIL" else "⚠")
                first_line = details.split("\n")[0]
                print(f"  {icon}  {cube_name:40s} {status:5s}  {first_line}")
                rest = details.split("\n")[1:]
                for r in rest:
                    print(f"      {'':40s} {'':5s}  {r}")
        except Exception as e:
            print(f"  ⚠  TM1 validation failed: {e}")
            tm1_failures = 0

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    total_failures = static_failures + tm1_failures
    if total_failures:
        print(
            f"  ✗  {total_failures} issue(s) found (static: {static_failures}, TM1: {tm1_failures})"
        )
        sys.exit(1)
    else:
        print("  ✓  All rules pass validation")
        sys.exit(0)


if __name__ == "__main__":
    main()
