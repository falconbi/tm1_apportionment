# tm1_apportionment — CLAUDE.md
> AI context file for this repository. Read this fully before writing any code.

---

## Repository identity
- **Repo**       : `~/apps/tm1_apportionment/`
- **Purpose**    : Builds and maintains the CST Apportionment module for
                   IBM Planning Analytics V12. Implements Activity Based
                   Costing (ABC) using apportionment methodology.
- **Standalone** : Completely independent 

## Server addresses
| Service               | Address                                           |
|-----------------------|---------------------------------------------------|
| TM1 V12 (Windows VM)  | `192.168.1.178:4444`                              |
| PAW (RHEL VM)         | `192.168.1.223`                                   |
| Authentik (identity)  | `192.168.1.171:9000`                              |
| PAW restart           | `cd ~/paw/paw31/scripts && sudo ./paw.sh restart` |

---

## CRITICAL — TM1py rules for this V12 environment
> Hard rules. Do not use any other TM1py attribute methods.

### Rule 1 — Attribute writes: two methods only

**Alias attributes only** — use `write_values`:
```python
cube_name = f"}ElementAttributes_{DIM}"
dims      = [DIM, f"}ElementAttributes_{DIM}"]
cells     = {(element, 'AttrName'): value, ...}
tm1.cells.write_values(cube_name, cells, dimensions=dims)
```

**String attributes OR mix of Alias and String** — use `write_through_unbound_process`:
```python
cube_name = f"}ElementAttributes_{DIM}"
dims      = [DIM, f"}ElementAttributes_{DIM}"]
cells     = {(element, 'AttrName'): value, ...}
tm1.cells.write_through_unbound_process(cube_name, cells, dimensions=dims)
```

Never use `update_attribute_values`, `set_attribute`, or any other
TM1py attribute method — they do not exist in this V12 patched version.


## Architecture

etl/run_apportionment.py
  ├── Gate check: reads VAL01–VAL06 from TM1 — blocks on FAIL, warns on WARNING
  ├── Stage 1b: Pool → Pool iterative Python
  ├── Stage 2b: Activity → Activity iterative Python
  └── RC check: reads RC01/RC02/RC03/RC04/RC05/RC06 from TM1 rules — reports PASS/FAIL
```

**TM1 rules** handle all apportionment calculations (Stages 1, 2, 3) live on demand.
**Python** handles iterative reciprocal stages (1b, 2b) and gate validation.
**No Flask, no NumPy matrix solver** — pure Python iteration.

---

## Period range — version-driven
Period lists are always driven by `Start Period` and `End Period` element attributes
on GBL Version in TM1. Never hardcode period lists.

```python
from etl.utils import get_version_periods
periods = get_version_periods(tm1, 'Budget')
# → ['2026-04', '2026-05', ..., '2027-03']
```

ETL scripts accept `--version Budget` (no `--period`) to process all version periods.
Single period override: `--period 2026-04 --version Budget`

---

## Validation gate — VAL checks

| Check | What it validates | Status | Written by |
|-------|-------------------|--------|------------|
| VAL01 | Pool Config — all pools have driver percentage shares configured | FAIL if any pool missing | val_checks.py |
| VAL02 | Activity Config — all activities have input volumes configured | FAIL if any activity missing | val_checks.py |
| VAL03 | Driver SQL vs TM1 spot-check — TM1 loaded values match SQL source totals | FAIL if mismatch > tolerance | val_checks.py |
| VAL04 | Account Config — all overhead accounts have pool assignments (Driver % sums to 100) | FAIL if any account unassigned | val_checks.py |
| VAL05 | Account Config — all Direct accounts have Direct % configured (sums to 100) | FAIL if any direct account missing % | val_checks.py |
| VAL06 | Account Config — no accounts with blank Apportionment Type | FAIL if any account type is blank | val_checks.py |

Status values: `PASS` / `WARNING` / `FAIL` / `NO DATA`
- **FAIL** — gate blocks apportionment (override with `--force`)
- **WARNING** — gate passes, apportionment runs with interim numbers
- P2P and A2A driver completeness = WARNING not FAIL (missing = reciprocal skipped, valid if not configured)
- VAL03 requires SQL source connection — skipped with WARNING if unavailable.

---

## Reconciliation checks — RC checks

| Check | Stage | Input | Output |
|-------|-------|-------|--------|
| RC01 | Stage 1: Account → Pool | GL Amount at `Input` cost pool | Apportioned Amount at `Total Cost Pools` |
| RC02 | Stage 1b: Pool Reciprocal | Pool Base Amount vs Final Balance | Pool Reciprocal Balance |
| RC03 | Stage 2: Pool → Activity | Amount at `Input` activity | Apportioned Amount at `Total Activities` |
| RC04 | Stage 2b: Activity Reciprocal | Activity Base Amount vs Final Balance | Activity Reciprocal Balance |
| RC05 | Stage 3: Activity → Service Line | Amount at `Input` service line | Apportioned Amount at `Total Service Lines` |
| RC06 | End-to-End: GL Input = Service Line Output | GL Input at `Input` | Post Apportionment at `Total Service Lines` |

RC checks are always-live TM1 rules in `CST Apportionment Reconciliation`.
Status: `PASS` if `ABS(Variance) <= 0.01`, `FAIL` otherwise, `NO DATA` if Input Total = 0.

---

## Cube inventory (10 cubes)

| Stage | Cube | Key dimensions |
|-------|------|----------------|
| 1 Config | CST Account Config | Period, Version, Account, Cost Centre, Cost Pool, Measure |
| 1 Output | CST Account to Pool Apportionment | Period, Version, Cost Pool, Cost Centre, Account, Measure |
| 1b Config | CST Pool to Pool Config | Period, Version, Cost Pool, Cost Pool Dest, Cost Centre, Measure — `Active` flag defines valid CP→CP pairs; `Driver Value` drives normalised split; self-row (CP01→CP01) handles retention |
| 2 Config | CST Pool Config | Period, Version, Cost Pool, Driver, Activity, Measure |
| 2 Output | CST Pool to Activity Apportionment | Period, Version, Activity, Cost Pool, Cost Centre, Measure |
| 2b Config | CST Activity to Activity Config | Period, Version, Activity, Activity Dest, Cost Centre, Measure |
| 3 Config | CST Activity Config | Period, Version, Activity, Driver, Service Line, Measure |
| 3 Output | CST Activity to Service Line Apportionment | Period, Version, Service Line, Activity, Cost Centre, Measure |
| Output | CST Profit and Loss Report | Period, Version, Account, Service Line, Cost Centre, Stage, Measure |
| Audit | CST Apportionment Reconciliation | Period, Version, Reconciliation Check, Measure |

---

## Dimension inventory

| Dimension | Elements | Notes |
|-----------|----------|-------|
| CST Cost Pool | CP01–CP09 | Code & Desc alias, Input sentinel (weight 0) |
| CST Cost Pool Dest | CP01–CP09 | Mirror of Cost Pool — reciprocal destination |
| CST Activity | A01–A11 | Code & Desc alias, Input sentinel (weight 0) |
| CST Activity Dest | A01–A11 | Mirror of Activity — reciprocal destination |
| CST Service Line | SL01–SL08 | Code & Desc alias, Input sentinel (weight 0) |
| CST Driver | FLOORSPACE, HEADCOUNT, ASSETVALUE, POWERUSAGE, BEDDAYS, TRANSACTIONS | |
| CST Reconciliation Check | RC01–RC06, VAL01–VAL06 | RC = TM1 rules; VAL = Python written |
| CST Apportionment Stage | Pre/Post Apportionment | Flat, Desc alias |
| GBL Cost Centre | (GBL owned) + Input sentinel | Input added as orphan — no consolidation edge |

### Input sentinel pattern
All coded CST dimensions have an `Input` element at weight 0 under their consolidation.
Used to store cross-cube values where the dimension is not logically applicable.
Example: Pool Config stores basis string at `CST Activity = 'Input'`.

---


## ETL run sequence (per version)
```bash
Drivers loaded in TM1 by TI Process from CSV files 
python3 etl/val_checks.py --version Budget
python3 etl/run_apportionment.py --version Budget
# or single period:
python3 etl/run_apportionment.py --period 2026-04 --version Budget
# force past WARNING/FAIL gate:
python3 etl/run_apportionment.py --version Budget --force
```
---

## Naming conventions
- Prefix  : `CST` on all objects
- Spacing : single space — `CST Cost Pool` not `CSTCostPool`
- Case    : title case for dimension and cube names
- Elements: Code & Desc alias — element = `CP01`, alias = `CP01 Facilities`
- Dest dims: exact mirrors of originals — same elements, same aliases
- Cubes   : flow naming — `CST [Source] to [Destination] Apportionment`

---

## Design decisions log

| Decision | Choice | Reason |
|----------|--------|--------|
| Apportionment engine | TM1 rules (Stages 1/2/3) + Python iteration (1b/2b) | Rules handle live calculations; Python handles reciprocal iteration |
| Gate check | VAL01–VAL06 PASS/WARNING/FAIL | Protects apportionment from incomplete data; WARNING allows interim runs |
| Period range source | TM1 GBL Version Start/End Period attributes | Single source of truth — no hardcoded period lists |
| Stage 1b P2P config basis | Driver Value + Active flag | Active (1/0) defines valid CP→CP relationships. Driver Values normalised across Active=1 intersections only. |
| Direct vs Indirect costs | Apportionment Type flag + Direct Service Line % | `Apportionment Type` (Direct/Indirect/Excluded) at Account/CC level. |
| Git strategy | Single repo, main branch, no remote yet | Binary `.db` files excluded. |
---

### Environment config
One connection config per environment — same deploy scripts, different server:
- `config/dev.json`
- `config/test.json`
- `config/prod.json`


---

## Pending — not yet built

**Still to build:**

