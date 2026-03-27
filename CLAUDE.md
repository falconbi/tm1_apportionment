# tm1_apportionment — CLAUDE.md
> AI context file for this repository. Read this fully before writing any code.

---

## Repository identity
- **Repo**       : `~/apps/tm1_apportionment/`
- **Purpose**    : Builds and maintains the CST Apportionment module for
                   IBM Planning Analytics V12. Implements Activity Based
                   Costing (ABC) using apportionment methodology.
- **Standalone** : Completely independent — no imports from tm1_governance
                   or tm1_global
- **Depends on** : tm1_global must be built first — GBL dimensions must
                   exist on the TM1 server before CST builds run

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
cube_name = f"}}ElementAttributes_{DIM}"
dims      = [DIM, f"}}ElementAttributes_{DIM}"]
cells     = {(element, 'AttrName'): value, ...}
tm1.cells.write_values(cube_name, cells, dimensions=dims)
```

**String attributes OR mix of Alias and String** — use `write_through_unbound_process`:
```python
cube_name = f"}}ElementAttributes_{DIM}"
dims      = [DIM, f"}}ElementAttributes_{DIM}"]
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
- **RC checks (RC01, RC03, RC05)** — always-live TM1 rules reading from apportionment cubes
- **VAL checks (VAL01–VAL04)** — Python-written stored string values (Status + Message)
- Status/Variance rules must use element qualifiers per RC check so VAL cells are NOT covered by rules and remain writable by Python:
```
['Status','CST Reconciliation Check':'RC01'] = S: IF(...);
['Status','CST Reconciliation Check':'RC03'] = S: IF(...);
```

---

## Terminology — critical
- **Apportionment** throughout — never "Allocation"
- Apportionment = distributing a shared cost using a chosen driver basis
- Must be reflected in all object names, variable names, comments, print statements

---

## Architecture

```
SQL (SQLite test DB)
      │
      ▼
etl/load_gl.py          — loads GL amounts + Is Apportioned flag → CST Account Config
etl/load_drivers.py     — loads driver config → Pool/Activity Config cubes
                        — writes VAL01–VAL04 gate checks → CST Apportionment Reconciliation
      │
      ▼
etl/run_apportionment.py
  ├── Gate check: reads VAL01–VAL04 from TM1 — blocks on FAIL, warns on WARNING
  ├── Stage 1b: Pool → Pool iterative Python (placeholder — not yet built)
  ├── Stage 2b: Activity → Activity iterative Python (placeholder — not yet built)
  └── RC check: reads RC01/RC03/RC05 from TM1 rules — reports PASS/FAIL
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
# → ['2025-04', '2025-05', ..., '2026-03']
```

ETL scripts accept `--version Budget` (no `--period`) to process all version periods.
Single period override: `--period 2025-04 --version Budget`

---

## Validation gate — VAL checks

| Check | What it validates | Status | Written by |
|-------|-------------------|--------|------------|
| VAL01 | Pool Config — all pools have driver percentage shares configured | FAIL if any pool missing | run_apportionment.py |
| VAL02 | Activity Config — all activities have input volumes configured | FAIL if any activity missing | run_apportionment.py |
| VAL03 | Driver SQL vs TM1 spot-check — TM1 loaded values match SQL source totals | FAIL if mismatch > tolerance | run_apportionment.py |
| VAL04 | Account Config — all overhead accounts have pool assignments (Driver % sums to 100) | FAIL if any account unassigned | run_apportionment.py |
| VAL05 | Account Config — all Direct accounts have Direct % configured (sums to 100) | FAIL if any direct account missing % | run_apportionment.py |
| VAL06 | Account Config — no accounts with blank Apportionment Type | FAIL if any account type is blank | run_apportionment.py |

Status values: `PASS` / `WARNING` / `FAIL` / `NO DATA`
- **FAIL** — gate blocks apportionment (override with `--force`)
- **WARNING** — gate passes, apportionment runs with interim numbers
- P2P and A2A driver completeness = WARNING not FAIL (missing = reciprocal skipped, valid if not configured)
- VAL03 requires SQL source connection — skipped with WARNING if unavailable

---

## Reconciliation checks — RC checks

| Check | Stage | Input | Output |
|-------|-------|-------|--------|
| RC01 | Stage 1: Account → Pool | GL Amount at `Input` cost pool | Apportioned Amount at `Total Cost Pools` |
| RC03 | Stage 2: Pool → Activity | Amount at `Input` activity | Apportioned Amount at `Total Activities` |
| RC05 | Stage 3: Activity → Service Line | Amount at `Input` service line | Apportioned Amount at `Total Service Lines` |

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
| CST Reconciliation Check | RC01–RC06, VAL01–VAL04 | RC = TM1 rules; VAL = Python written |
| CST Apportionment Stage | Pre/Post Apportionment | Flat, Desc alias |
| GBL Cost Centre | (GBL owned) + Input sentinel | Input added as orphan — no consolidation edge |

### Input sentinel pattern
All coded CST dimensions have an `Input` element at weight 0 under their consolidation.
Used to store cross-cube values where the dimension is not logically applicable.
Example: Pool Config stores basis string at `CST Activity = 'Input'`.

---

## Rules inventory (YAML source of truth)

| File | Cube | What it does |
|------|------|--------------|
| `cst_account_config.yaml` | CST Account Config | Feeders to Stage 1 apportionment cube |
| `cst_account_to_pool_apportionment.yaml` | CST Account to Pool Apportionment | Amount, Rate, Apportioned Amount rules + feeders to Stage 2 + RC01 feeders |
| `cst_pool_config.yaml` | CST Pool Config | Driver Pct Share rule + feeders to Stage 2 apportionment rate — self-feeder uses `Total Activities` consolidation (fixed bug: was using invalid `!CST Pool Config Measure` variable) |
| `cst_pool_to_activity_apportionment.yaml` | CST Pool to Activity Apportionment | Amount, Rate, Apportioned Amount rules + feeders to Stage 3 + RC03 feeders — Apportioned Amount uses Stage 1b Complete cross-cube flag to choose SA vs Amount |
| `cst_activity_config.yaml` | CST Activity Config | Driver Pct Share rule + feeders to Stage 3 apportionment rate |
| `cst_activity_to_service_line_apportionment.yaml` | CST Activity to Service Line Apportionment | Amount, Rate, Apportioned Amount, Per Unit rules + RC05 feeders |
| `cst_apportionment_reconciliation.yaml` | CST Apportionment Reconciliation | RC01/RC03/RC05 Input Total, Output Total, Variance, Status rules |

Deploy all rules:
```bash
python3 model_builder/deploy_rules.py
```
Deploy single rule:
```bash
python3 model_builder/deploy_rules.py cst_account_config
```

---

## Views inventory (YAML source of truth)

Views follow the `RPT <Description>` naming convention. Each cube has at least one `RPT Default` view with `set_as_default: true`. Additional views use descriptive names.
Deploy: `python3 model_builder/deploy_views.py`

### View conventions
- **Columns** — dynamic period range using `STRTOMEMBER` + `Start Period`/`End Period` GBL Version properties
- **Rows** — relevant business dimensions crossed together (Cost Pool × Activity etc.)
- **Slicer (WHERE)** — Version pinned to Budget; measure pinned to most useful default; Cost Centre at `Total Cost Centres` for apportionment output cubes
- **NON EMPTY** on both axes to suppress zero/blank cells

> **Note:** `CST Pool to Pool Apportionment`, `CST Activity to Activity Apportionment`, and `CST Profit and Loss Report` still use a static period slicer (`Apr FY2025`) — these need updating to dynamic period range when Stage 1b/2b are built.

| File | Cube | Rows | Columns | Default slicer |
|------|------|------|---------|----------------|
| `cst_account_config.yaml` | CST Account Config | Account × Cost Centre × Cost Pool | Period range | Driver Percentage Share |
| `cst_account_to_pool_apportionment.yaml` | CST Account to Pool Apportionment | TOTAL OVERHEAD drilldown × Cost Pool | Period range | Apportioned Amount, Total Cost Centres |
| `cst_pool_config.yaml` | CST Pool Config | Cost Pool × Driver × Activity | Period range | Pool to Activity Basis |
| `cst_pool_to_activity_apportionment.yaml` | CST Pool to Activity Apportionment | Cost Pool × Activity | Period range | Apportioned Amount, Total Cost Centres |
| `cst_pool_to_pool_config.yaml` | CST Pool to Pool Config | Cost Pool Dest × Cost Pool | Period range × all measures | Input CC — 3 views: RPT Default (all measures), RPT Pool to Pool Active (Active flag entry, no NON EMPTY on rows), RPT Driver Value By Cost Centre (expanded CCs) |
| `cst_pool_to_pool_apportionment.yaml` | CST Pool to Pool Apportionment | Cost Pool (rows) | Cost Centre × Cost Pool Dest (cols) | Apportioned Amount — **static period** |
| `cst_activity_config.yaml` | CST Activity Config | Activity × Driver × Service Line | Period range | Activity to Service Line Basis |
| `cst_activity_to_service_line_apportionment.yaml` | CST Activity to Service Line Apportionment | Activity × Service Line | Period range | Apportioned Amount, Total Cost Centres |
| `cst_activity_to_activity_config.yaml` | CST Activity to Activity Config | Activity × Activity Dest × Cost Centre | Period range | Driver Value |
| `cst_activity_to_activity_apportionment.yaml` | CST Activity to Activity Apportionment | Activity (rows) | Cost Centre × Activity Dest (cols) | Apportioned Amount — **static period** |
| `cst_profit_and_loss_report.yaml` | CST Profit and Loss Report | Account (rows) | Service Line × Cost Centre (cols) | Amount, Post Apportionment — **static period** |
| `cst_apportionment_reconciliation.yaml` | CST Apportionment Reconciliation | Reconciliation Check × Measure | Period range (Budget version) | Budget version |

---

## Subsets inventory (YAML source of truth)

All subsets use `TM1FILTERBYLEVEL` to return leaf elements only (excludes consolidations).
Deploy: `python3 model_builder/deploy_subsets.py`

| File | Dimension | Subset name | MDX |
|------|-----------|-------------|-----|
| `cst_cost_pool.yaml` | CST Cost Pool | All Cost Pools | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |
| `cst_cost_pool_dest.yaml` | CST Cost Pool Dest | All Cost Pool Dests | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |
| `cst_activity.yaml` | CST Activity | All Activities | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |
| `cst_activity_dest.yaml` | CST Activity Dest | All Activity Dests | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |
| `cst_service_line.yaml` | CST Service Line | All Service Lines | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |
| `cst_driver.yaml` | CST Driver | All Drivers | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |
| `cst_reconciliation_check.yaml` | CST Reconciliation Check | All Checks | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |
| `cst_etl_job.yaml` | CST ETL Job | All ETL Jobs | `TM1FILTERBYLEVEL({TM1SUBSETALL(...)}, 0)` |

---

## Directory structure
```
~/apps/tm1_apportionment/
├── CLAUDE_tm1_apportionment.md
├── config.py
├── tm1py_connect.py
├── requirements.txt                    (TM1py, requests, numpy, flask)
├── model_builder/
│   ├── build_cst_model.py              ← orchestrator — run this to build
│   ├── cleanup_cst_model.py            ← safe on empty server
│   ├── create_cst_dimensions.py        ← all CST dimensions + measure dims
│   ├── create_cst_apportionment_stage.py
│   ├── create_cst_cubes.py             ← all 10 CST cubes
│   ├── deploy_rules.py                 ← deploys rules/*.yaml to TM1
│   ├── deploy_views.py                 ← deploys views/*.yaml to TM1
│   ├── deploy_processes.py             ← deploys ti_processes/*.yaml to TM1
│   ├── deploy_subsets.py
│   ├── generate_model_store.py
│   └── gbl_check.py                    ← prerequisite guard
├── etl/
│   ├── utils.py                        ← get_version_periods() helper
│   ├── load_gl.py                      ← loads GL data → CST Account Config
│   ├── load_drivers.py                 ← loads driver config → Config cubes + VAL checks
│   └── run_apportionment.py            ← gate check + RC reporting
├── rules/                              ← YAML rule files (source of truth)
│   ├── cst_account_config.yaml
│   ├── cst_account_to_pool_apportionment.yaml
│   ├── cst_pool_config.yaml
│   ├── cst_pool_to_activity_apportionment.yaml
│   ├── cst_activity_config.yaml
│   ├── cst_activity_to_service_line_apportionment.yaml
│   └── cst_apportionment_reconciliation.yaml
├── views/                              ← YAML view files (one per cube)
├── subsets/                            ← YAML subset files
├── ti_processes/                       ← YAML TI process definitions
└── tests/
    └── data/
        └── cst_test_data.db            ← SQLite test database (excluded from git — binary)
```

---

## Build sequence
```bash
# Prerequisites — tm1_global must be built first

cd ~/apps/tm1_apportionment
python3 model_builder/cleanup_cst_model.py    # safe on empty server
python3 model_builder/build_cst_model.py      # full build
```

## ETL run sequence (per version)
```bash
python3 etl/load_drivers.py --version Budget
python3 etl/load_gl.py --version Budget
python3 etl/run_apportionment.py --version Budget
# or single period:
python3 etl/run_apportionment.py --period 2025-04 --version Budget
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
| Allocation vs Apportionment | Apportionment | Accurate — costs are shared not directly traced |
| Apportionment engine | TM1 rules (Stages 1/2/3) + Python iteration (1b/2b) | Rules handle live calculations; Python handles reciprocal iteration |
| No Flask / NumPy matrix solver | Pure Python iteration | Simpler, easier to debug, no API layer needed |
| Gate check | VAL01–VAL04 PASS/WARNING/FAIL | Protects apportionment from incomplete data; WARNING allows interim runs |
| VAL01 missing drivers | WARNING not FAIL | Pools with no driver values apportion zero — valid in production |
| Period range source | TM1 GBL Version Start/End Period attributes | Single source of truth — no hardcoded period lists |
| Rules storage | YAML files in rules/ | Git as source of truth; deploy_rules.py pushes to TM1 |
| Views storage | YAML files in views/ | All views set_as_default: true |
| Reciprocal method | Iterative Python (Stage 1b/2b) | Subsumes sequential as special case; handles all ABC patterns |
| Activity to Activity | Included (Stage 2b) | Common in knowledge/process industries |
| Cross-period interactions | Phase 3 deferred | Complex, low priority |
| Stage 1b Complete flag | Stored in CST Apportionment Reconciliation at (period, version, RC03, Stage 1b Complete) | Self-referential DB() consolidation reads return 0 in N: rules — cross-cube flag avoids this |
| Stage 2 Apportioned Amount fallback | Uses Settled Amount post-Stage 1b, Amount pre-Stage 1b | Controlled by Stage 1b Complete cross-cube flag — see above |
| ETL trigger mechanism | CST ETL Control cube + Python poller | TM1 V12 has no ExecuteCommand — poller reads Status=REQUESTED and dispatches ETL |
| Stage 1b P2P config basis | Driver Value + Active flag | Active (1/0) defines valid CP→CP relationships. Driver Values normalised across Active=1 intersections only. Self-row (CP01→CP01) handles partial retention. No Active entry = pool not redistributed. |
| Direct vs Indirect costs | Apportionment Type flag + Direct Service Line % | `Apportionment Type` (Direct/Indirect/Excluded) at Account/CC level. Direct costs bypass ABC chain, route to Service Line via explicit % split. `CST Service Line` dimension to be added to `CST Account Config` — `Input` sentinel used where not applicable. |
| Sub-Service Line structure | PA Virtual Dimensions (Hierarchies) — deferred | Granular SL leaves with multiple hierarchy groupings. No cube redesign needed. Implement when sub-SL reporting is required. |
| Git strategy | Single repo per module, master branch, no remote yet | `tm1_apportionment` initialised. Remote and dev/test/main branching to be set up. Binary `.db` files excluded. |

## CI/CD pipeline

### Git branching strategy
Branches map to environments:
- `dev` — development rig, active development
- `test` — promoted from dev via pull request
- `main` — production, promoted from test via pull request

Promotion flow: `dev → PR → test → PR → main`

### Model as code — declarative deploy
All TM1 model objects are defined in YAML files and deployed by Python scripts.
No manual Architect work between environments. Git diff shows exactly what changed.

Current state of declarative coverage:

| Object type | Folder | Deploy script | Status |
|-------------|--------|---------------|--------|
| Rules | `rules/` | `deploy_rules.py` | ✓ Done |
| Views | `views/` | `deploy_views.py` | ✓ Done |
| Subsets | `subsets/` | `deploy_subsets.py` | ✓ Done |
| TI Processes | `ti_processes/` | `deploy_processes.py` | In progress |
| Dimensions | `dimensions/` | `deploy_dimensions.py` | Not yet built |
| Cubes | `cubes/` | `deploy_cubes.py` | Not yet built |
| Chores | `chores/` | `deploy_chores.py` | Not yet built |

Full deploy sequence (dependency order):
```bash
python3 model_builder/deploy_dimensions.py
python3 model_builder/deploy_cubes.py
python3 model_builder/deploy_rules.py
python3 model_builder/deploy_subsets.py
python3 model_builder/deploy_views.py
python3 model_builder/deploy_processes.py
python3 model_builder/deploy_chores.py
# or when built:
python3 model_builder/deploy_all.py
```

### Environment config
One connection config per environment — same deploy scripts, different server:
- `config/dev.json`
- `config/test.json`
- `config/prod.json`

Not yet built — currently `config.py` / `tm1py_connect.py` handles single server.

### Drift detection
Run `export_model.py` against any environment, compare JSON output to repo.
Git diff shows exactly what drifted. Not yet built.

### Rule — no manual Architect changes on test or prod
Everything goes through the pipeline. Manual changes in Architect get overwritten on next deploy.

---

## Pending — not yet built

**Next up — agreed design, not yet implemented:**
- Update `CST Account Config` cube — add `CST Service Line` dimension
- Replace `Is Apportioned` with `Apportionment Type` (String: Direct/Indirect/Excluded)
- Add `Direct %` measure to `CST Account Config Measure`
- Update ETL, rules, views and test data for direct/indirect routing
- Update `_run_stage1b()` to filter P2P reads by `Active = 1`

**Still to build:**
- Stage 2b Activity → Activity iterative solver
- RC02, RC04, RC06 reconciliation checks (reciprocal balance + end-to-end)
- GBL Assumptions cube in tm1_global (META DATA GBL Version TI errors until built)
- Remote git repo + dev/test/main branch structure
- Production infrastructure docs (systemd service for poller, environment config per environment)

## Recently built
- Stage 1b Pool → Pool reciprocal iteration — converges in ~11 iterations, tolerance 0.01
- Stage 1b Complete cross-cube flag — written by Python to Reconciliation cube after convergence
- CST ETL Control cube + Python poller (`etl/poller.py`) — job queue pattern replacing ExecuteCommand
- TI wrapper processes: CST Load Drivers, CST Load GL Data, CST Run Apportionment
- Default subsets for all CST dimensions
- Config-driven overhead_consolidation (`config.py CST_CONFIG`) — substituted into rules/views at deploy time
- P2P Active flag — `CST Pool to Pool Config Measure` + SQL test data + load process updated
- Git initialised — `.db` files excluded, 3 commits on master
