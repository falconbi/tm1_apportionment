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

### Rule 2 — Alias uniqueness
TM1 enforces uniqueness on Alias type attributes across a dimension.
If two elements may share the same description — declare as String type
and use `write_through_unbound_process`.

### Rule 3 — Cleanup scripts never fail on not found
Always exit 0. Not found = already clean = success.
Use dynamic discovery:
```python
cst_cubes = [c for c in tm1.cubes.get_all_names() if c.startswith('CST')]
for name in cst_cubes:
    try:
        tm1.cubes.delete(name)
        print(f"  ✓ {name}")
    except Exception as e:
        print(f"  ✗ {name} — {e}")
```

### Rule 4 — Cube dimension order (non-negotiable)
```
1. GBL Period
2. GBL Version
3. Business/structural dimensions in logical order
4. Measure dimension always last
```

### Rule 5 — Cube data writes
- **Numeric measures** — use `write_values` (bulk dict write):
  ```python
  tm1.cells.write_values(CUBE, cells, dimensions=DIMS)
  ```
- **String measures** — use `write_value` (single cell):
  ```python
  tm1.cells.write_value(value, CUBE, (dim1, dim2, ...), dimensions=DIMS)
  ```
- Do NOT use `write_values` for string cells — raises `StringCellUpdateError`
- Do NOT write to consolidation elements via REST API — TM1 rejects them with a misleading "element not found" error. Always write to leaf elements. Use `Input` sentinel where a dimension is not logically applicable.

### Rule 6 — Rules: SKIPCHECK + FEEDSTRINGS mandatory
Every rule file must open with:
```
SKIPCHECK;
FEEDSTRINGS;
```

### Rule 7 — Feeder pattern
Read the N: rule backwards to write the feeder. Feeder goes in the **source** cube's rule file.
- Pin ALL fixed dimensions on LHS using element qualifiers
- Use `!DimName` on RHS — resolves to the pinned element
- When feeding a cube that has a dimension not in the source, hard-code a consolidation element so all leaves beneath it are fed
- Multiple feeder targets: comma-separated in one statement

```
# Source cube rule:
['Apportioned Amount'] = N: ['Amount'] * ['Apportionment Rate'] / 100;

# Feeder in the SAME cube (reads the rule backwards):
['Apportioned Amount'] =>
    DB('CST Pool to Activity Apportionment', !GBL Period, !GBL Version,
       'Total Activities', !CST Cost Pool, 'Total Cost Centres', 'Amount');
```

Cross-cube dimension pinning syntax: `'DimName':'ElementName'`
```
DB('CST Pool Config', !GBL Period, !GBL Version, !CST Cost Pool,
   'GBL Cost Centre':'Total Cost Centres', 'CST Activity':'Input', 'Driver Percentage Share')
```

### Rule 8 — VAL vs RC split in Reconciliation cube
- **RC checks (RC01, RC02, RC03, RC04, RC05, RC06)** — always-live TM1 rules reading from apportionment cubes
- **VAL checks (VAL01–VAL06)** — Python-written stored string values (Status + Message) in `etl/val_checks.py`
- Status/Variance rules must use element qualifiers per RC check so VAL cells are NOT covered by rules and remain writable by Python:
```
['Status','CST Reconciliation Check':'RC01'] = S: IF(...);
['Status','CST Reconciliation Check':'RC03'] = S: IF(...);
```


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

## Rules inventory (source of truth)

| File | Cube | What it does |
|------|------|--------------|
| `cst_account_config.yaml` | CST Account Config | Feeders to Stage 1 apportionment cube |
| `cst_account_to_pool_apportionment.yaml` | CST Account to Pool Apportionment | Amount, Rate, Apportioned Amount rules + feeders to Stage 2 + RC01 feeders |
| `cst_pool_config.yaml` | CST Pool Config | Driver Pct Share rule + feeders to Stage 2 apportionment rate — self-feeder uses `Total Activities` consolidation |
| `cst_pool_to_activity_apportionment.yaml` | CST Pool to Activity Apportionment | Amount, Rate, Apportioned Amount rules + feeders to Stage 3 + RC03 feeders — Apportioned Amount uses Stage 1b Complete cross-cube flag to choose SA vs Amount |
| `cst_activity_config.yaml` | CST Activity Config | Driver Pct Share rule + feeders to Stage 3 apportionment rate |
| `cst_activity_to_service_line_apportionment.yaml` | CST Activity to Service Line Apportionment | Amount, Rate, Apportioned Amount, Per Unit rules + RC05 feeders |
| `cst_apportionment_reconciliation.yaml` | CST Apportionment Reconciliation | RC01-RC06 Input Total, Output Total, Variance, Status rules |

Deploy all rules:
```bash
python3 model_builder/deploy_rules.py
```

---

## Directory structure
```
~/apps/tm1_apportionment/
├── CLAUDE.md
├── config.py
├── tm1py_connect.py
├── requirements.txt
├── model_builder/
│   ├── build_cst_model.py              ← orchestrator — run this to build
│   ├── cleanup_cst_model.py            ← safe on empty server
│   ├── create_cst_dimensions.py        ← all CST dimensions + measure dims
│   ├── create_cst_cubes.py             ← all 10 CST cubes
│   ├── deploy_rules.py                 ← deploys rules/*.rux to TM1
│   ├── deploy_views.py                 ← deploys views/*.yaml to TM1
│   ├── deploy_processes.py             ← deploys ti_processes/*.yaml to TM1
│   └── deploy_subsets.py
├── etl/
│   ├── utils.py                        ← get_version_periods() helper
│   ├── load_gl.py                      ← loads GL data → CST Account Config
│   ├── val_checks.py                   ← VAL01–VAL06 pre-flight checks
│   └── run_apportionment.py            ← gate check + RC reporting
├── rules/                              ← TM1 rule files (.rux)
├── views/                              ← View files
├── subsets/                            ← Subset files
├── ti_processes/                       ← TI process definitions
└── sample_data/                        ← CSV test data files
```

---

## Build sequence
```bash
# Prerequisites — tm1_global must be built first.

cd ~/apps/tm1_apportionment
python3 model_builder/cleanup_cst_model.py    # safe on empty server
python3 model_builder/build_cst_model.py      # full build
```

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
| VAL01 missing drivers | WARNING not FAIL | Pools with no driver values apportion zero — valid in production |
| Period range source | TM1 GBL Version Start/End Period attributes | Single source of truth — no hardcoded period lists |
| Rules storage | .rux files in rules/ | TM1 as source of truth; deploy_rules.py pushes to TM1 |
| Stage 1b P2P config basis | Driver Value + Active flag | Active (1/0) defines valid CP→CP relationships. Driver Values normalised across Active=1 intersections only. |
| Direct vs Indirect costs | Apportionment Type flag + Direct Service Line % | `Apportionment Type` (Direct/Indirect/Excluded) at Account/CC level. |
| Git strategy | Single repo, main branch, no remote yet | Binary `.db` files excluded. |

---

## CI/CD pipeline

### Git branching strategy
Branches map to environments:
- `dev` — development rig, active development
- `test` — promoted from dev via pull request
- `main` — production, promoted from test via pull request

Promotion flow: `dev → PR → test → PR → main`

### Environment config
One connection config per environment — same deploy scripts, different server:
- `config/dev.json`
- `config/test.json`
- `config/prod.json`

Not yet built — currently `config.py` / `tm1py_connect.py` handles single server.

---

## Pending — not yet built

**Next up — agreed design, not yet implemented:**
- RC02, RC04, RC06 reconciliation checks (reciprocal balance + end-to-end)
- `etl/val_checks.py` — VAL01–VAL06 pre-flight checks
- Remove `etl/load_drivers.py` (replaced by val_checks.py)
- Update `_run_stage1b()` to filter P2P reads by `Active = 1`

**Still to build:**
- GBL Assumptions cube in tm1_global (META DATA GBL Version TI errors until built)
- Remote git repo + dev/test/main branch structure
- Production infrastructure docs (systemd service for poller, environment config per environment)
