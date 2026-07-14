# CST Apportionment — Pigment Design Reference

Activity Based Costing with full reciprocal apportionment, designed for Pigment EPM.

This document describes the design in Pigment terms — Properties, Blocks, Formulas, and
Import flows. The source implementation is in IBM Planning Analytics (TM1); this document
maps that design directly to Pigment's architecture.

---

## Table of Contents

- [Design philosophy](#design-philosophy)
- [The apportionment chain](#the-apportionment-chain)
- [Properties (dimensions)](#properties)
- [Blocks (cubes)](#blocks)
- [Stage 1 — Account to Pool](#stage-1--account-to-pool)
- [Stage 1b — Pool to Pool reciprocal](#stage-1b--pool-to-pool-reciprocal)
- [Stage 2 — Pool to Activity](#stage-2--pool-to-activity)
- [Stage 2b — Activity to Activity reciprocal](#stage-2b--activity-to-activity-reciprocal)
- [Stage 3 — Activity to Service Line](#stage-3--activity-to-service-line)
- [Direct costs](#direct-costs)
- [Validation gate](#validation-gate)
- [Reconciliation checks](#reconciliation-checks)
- [Import flows](#import-flows)
- [Output and reporting](#output-and-reporting)
- [Design decisions](#design-decisions)

---

## Design philosophy

Shared costs — IT, Facilities, Finance, HR — are real costs that every service line consumes.
The question is not whether to allocate them, but how accurately.

Simple step-down allocation applies costs in one pass down a fixed hierarchy. It's easy but
wrong: it ignores the fact that shared services support each other. IT supports Finance, Finance
supports HR, HR supports IT. Ignoring those circular relationships produces distorted results
at the service line level.

This design uses **full reciprocal apportionment**. Costs flow through a network of Cost Pools
and Activities, including circular flows between pools and between activities. The engine
iterates until every loop has settled — mathematically equivalent to solving the Leontief
Input-Output model. The result is an exact answer, not an approximation.

**Key principles:**

- Every overhead dollar traces through to the service line that consumed it
- Circular cost relationships are fully resolved, not approximated
- Direct costs bypass the chain and route straight to service lines
- The system balances end-to-end: GL input = service line output (RC06)
- All configuration lives in data, not code — add a cost pool without touching formulas

---

## The apportionment chain

```
GL Accounts
    │
    ▼
Stage 1:  Account → Cost Pool          (formula — live)
    │
    ▼  [reciprocal iteration if pools share costs with each other]
Stage 1b: Pool → Pool                   (Python ETL — iterative solver)
    │
    ▼
Stage 2:  Pool → Activity               (formula — live)
    │
    ▼  [reciprocal iteration if activities share costs with each other]
Stage 2b: Activity → Activity           (Python ETL — iterative solver)
    │
    ▼
Stage 3:  Activity → Service Line       (formula — live)
    │
    ▼
CST P&L Report
```

Stages 1, 2, and 3 are **live formulas** — they recalculate whenever upstream data changes.
Stages 1b and 2b are **iterative** — they cannot be expressed as a closed-form formula and
require a Python ETL process that writes settled amounts back into Pigment.

---

## Properties

Pigment equivalent of TM1 dimensions. All CST-prefixed properties are module-owned.
GBL-prefixed properties are shared with other applications.

| Property | Elements | Notes |
| --- | --- | --- |
| **GBL Period** | Monthly — `2026-04`, `2026-05` … | Pigment native time dimension. Use Pigment's built-in time hierarchy. |
| **GBL Version** | Budget, Forecast, Actuals, … | Scenario dimension. Period range driven by Start/End Period attributes. |
| **GBL Account** | Chart of accounts leaf codes | 6xxx = Overhead, 5xxx = Direct. Hierarchy consolidates to Total Overhead / Total Direct. |
| **GBL Cost Centre** | CC01–CCnn + `Input` sentinel | `Input` = cross-cube sentinel for config values (see below). |
| **CST Cost Pool** | CP01–CP09 + `Input` sentinel | Code (`CP01`) + alias (`CP01 Facilities`). |
| **CST Cost Pool Dest** | CP01–CP09 + `Input` sentinel | Mirror of Cost Pool for Pool→Pool reciprocal config. |
| **CST Activity** | A01–A11 + `Input` sentinel | Code + alias. |
| **CST Activity Dest** | A01–A11 + `Input` sentinel | Mirror of Activity for Activity→Activity reciprocal config. |
| **CST Service Line** | SL01–SL08 + `Input` sentinel | Final cost objects — products, services, or profit centres. |
| **CST Driver** | FLOORSPACE, HEADCOUNT, ASSETVALUE, POWERUSAGE, BEDDAYS, TRANSACTIONS | The basis types used to split costs. |
| **CST Reconciliation Check** | RC01–RC06, VAL00–VAL06 | Audit dimension. RC = formula-driven; VAL = Python ETL written. |

### The Input sentinel pattern

All coded CST properties have an element named `Input`. This is a **sentinel** used to store
configuration values at intersections where the property is not logically applicable.

Example: Pool Config stores the basis string (e.g. "HEADCOUNT") at
`CST Activity = Input, CST Driver = Input`. The sentinel avoids needing a separate
single-value property for scalar config.

In Pigment this maps to a reserved element on each property. Filter it out of user-facing
reports and views.

---

## Blocks

One Pigment Block per apportionment cube. The Measure dimension in the TM1 design becomes
separate columns (metrics) within each block.

### Config blocks (user-maintained)

| Block | Key properties | Columns |
| --- | --- | --- |
| **Account Config** | Period, Version, Account, Cost Centre, Cost Pool, Service Line | Amount, Apportionment Type, Driver Percentage Share, Direct Percentage Share |
| **Pool Config** | Period, Version, Cost Pool, Driver, Activity | Pool to Activity Basis, Driver Value |
| **Pool to Pool Config** | Period, Version, Cost Pool, Cost Pool Dest, Cost Centre | Active, Driver Value, Redistribution Percentage, Driver Description |
| **Activity Config** | Period, Version, Activity, Driver, Service Line | Activity to Service Line Basis, Driver Value |
| **Activity to Activity Config** | Period, Version, Activity, Activity Dest, Cost Centre | Active, Driver Value, Redistribution Percentage, Driver Description, Base Amount, Final Balance |

### Calculation blocks (formula-driven or ETL-written)

| Block | Key properties | Columns |
| --- | --- | --- |
| **Account to Pool Apportionment** | Period, Version, Cost Pool, Cost Centre, Account | Apportioned Amount |
| **Pool to Activity Apportionment** | Period, Version, Activity, Cost Pool, Cost Centre | Settled Amount (ETL), Apportioned Amount (formula) |
| **Activity to Service Line Apportionment** | Period, Version, Service Line, Activity, Cost Centre | Settled Amount (ETL), Apportioned Amount (formula) |
| **P&L Report** | Period, Version, Account, Service Line, Cost Centre, Stage | Amount |
| **Apportionment Reconciliation** | Period, Version, Reconciliation Check | Status, Message, Input Total, Output Total, Stage 1b Complete, Stage 2b Complete |

---

## Stage 1 — Account to Pool

Distributes GL overhead account costs to cost pools based on Driver Percentage Share.

**Formula (Pigment):**

For each `(Period, Version, Cost Pool, Cost Centre)`:

```
Apportioned Amount =
  SUMIF(Account Config[Apportioned Amount],
        Account Config[Cost Pool] = this[Cost Pool],
        Account Config[Cost Centre] = this[Cost Centre])
```

Where `Account Config[Apportioned Amount]` is itself:

```
Account Config[Apportioned Amount] =
  Account Config[Amount] × Account Config[Driver Percentage Share] / 100
```

**Configuration required per account:**

| Column | Values | Meaning |
| --- | --- | --- |
| Apportionment Type | `Indirect` | Routes through the pool chain |
| | `Direct` | Bypasses pools — goes straight to Service Lines |
| | `Excluded` | Not apportioned at all |
| Driver Percentage Share | 0–100% (sums to 100 across pools per account/CC) | Split between pools |
| Cost Pool | CP01–CP09 | Which pool collects this account's costs |

**Direct accounts** bypass Stage 1 entirely. They are handled in Stage 3.

---

## Stage 1b — Pool to Pool reciprocal

Resolves circular cost flows between cost pools. For example: Facilities allocates to IT,
IT allocates back to Facilities. A single pass cannot resolve this — iteration is required.

**This stage is not a formula.** It runs as a Python ETL process outside Pigment, then writes
the settled amounts back. The Pigment formula for Apportioned Amount in Stage 2 reads the
`Settled Amount` column that Python writes.

### Configuration storage layout

`Pool to Pool Config` has properties: Period, Version, Cost Pool, Cost Pool Dest, Cost Centre.

Data is stored at specific element combinations — this is not obvious from the property list alone:

| What | Where stored | Notes |
| --- | --- | --- |
| Driver Value (pair-level) | Cost Pool × Cost Pool Dest, Cost Centre = **Input** | One raw volume per source→destination pair. No Cost Centre breakdown — stored at the Input sentinel. |
| Redistribution Percentage | Cost Pool × Cost Pool Dest = **Input**, Cost Centre = **Input** | One value per **source pool** only. Stored at `Cost Pool Dest = Input` — not per pair. |
| Base Amount | Cost Pool × Cost Pool Dest = **Input**, Cost Centre = **Input** | Written by Python ETL after each run. |
| Final Balance | Cost Pool × Cost Pool Dest = **Input**, Cost Centre = **Input** | Written by Python ETL after each run. |

`Cost Pool Dest = Input` is the sentinel meaning "this is a pool-level scalar, not a pair value."
Redistribution %, Base Amount, and Final Balance all live at this location for each source pool.

### Driver Values are raw volumes loaded from CSV, not percentages entered manually

Driver Values are **loaded from CSV files via an ETL import**, not entered manually in Pigment.
They are raw operational volumes (e.g. headcount count, floor area in sqm) sourced from
HR, facilities, or other operational systems and refreshed each period.

Python normalises them at runtime for each source pool:

```python
normalised_share[src][dest] = raw_driver_value[src][dest] / sum(raw_driver_values[src])
```

Do **not** pre-calculate percentages in the CSV or import — the normalisation must happen in
the solver so that adding or removing an Active pair automatically adjusts all shares.

In Pigment, these values should arrive via an **Import flow** (CSV or connected source), not
via a data entry screen. They are system data, not model assumptions.

### Redistribution Percentage

This is the fraction of a pool's total costs that get redistributed to other pools. The
remainder `(1 − Redistribution %)` is what flows forward to Stage 2 as the settled amount.

It is stored **once per source pool** at `Cost Pool Dest = Input`. It is not a per-pair value.

### Cost Centre handling

The iteration runs entirely on **pool totals** — Cost Centre is aggregated before the solver
and ignored during all iterations. After convergence, settled amounts are split back to Cost
Centre level using the **same proportional distribution as Stage 1**:

```python
ratio = settled_net_for_pool / original_pool_total   # one scalar per pool
settled_amount[pool][cc] = stage1_amount[pool][cc] × ratio
```

This assumes the reciprocal does not change the relative Cost Centre split within a pool —
only the pool total changes. Stage 2 receives settled amounts at full Cost Centre granularity.

### Algorithm

```python
# 1. Read Driver Values (Cost Pool × Cost Pool Dest at CC=Input) — raw volumes
# 2. Normalise to split percentages per source pool
# 3. Read Redistribution % per source pool (Cost Pool Dest=Input at CC=Input)
# 4. Read Stage 1 pool balances at Cost Pool × Cost Centre level (for CC split-back later)
# 5. Aggregate Stage 1 balances to pool totals (sum across all CCs)
# 6. Iterate on pool totals until convergence:
#      new_balance[pool] = original_balance[pool]
#                        + Σ src: balance[src] × redist%[src] × normalised_share[src→pool]
#    Stop when max change across all pools < 0.01 (tolerance, not a fixed iteration count)
#    Typically converges in ~11 iterations; safety cap at 100
# 7. Compute settled_net[pool] = final_balance[pool] × (1 − redist%[pool])
# 8. Split settled_net back to Cost Centre using Stage 1 proportional ratio
# 9. Write Settled Amount to Pool to Activity Apportionment (at CC level)
# 10. Write Base Amount and Final Balance to Pool to Pool Config (at Cost Pool Dest=Input)
# 11. Write Stage 1b Complete flag to Reconciliation block
```

### Convergence

Dynamic — not a fixed iteration count. The solver checks after every iteration:

```
if max(|new_balance[pool] − balance[pool]| for all pools) < 0.01: stop
```

The `--max-iter 100` flag is a safety cap against non-convergence (which would indicate
misconfigured circular config, not normal operation). The tolerance of 0.01 (1 cent) is
intentional — sub-cent differences are below financial reporting precision.

`Settled Amount` flows forward to Stage 2 as the input to Pool → Activity.

---

## Stage 2 — Pool to Activity

Distributes settled pool costs to activities based on driver percentages.

**Formula (Pigment):**

For each `(Period, Version, Activity, Cost Pool, Cost Centre)`:

```
Apportioned Amount =
  Pool to Activity Apportionment[Settled Amount]
  × LOOKUP(Pool Config[Pool to Activity Basis], Cost Pool, Activity)
  / 100
```

**Configuration required per pool:**

- `Pool to Activity Basis` — which driver type (e.g. HEADCOUNT) splits this pool's costs. Model assumption, manually maintained.
- `Driver Value` in `Pool Config` — the raw volume at each Activity/Driver intersection. **Loaded from CSV each period**, not entered manually.

Driver values are normalised across all activities for each pool before applying.

---

## Stage 2b — Activity to Activity reciprocal

Mirrors Stage 1b exactly, substituting Activities for Cost Pools.

Resolves circular flows between activities (e.g. HR Activity supports IT Activity, IT Activity
supports HR Activity). Python ETL writes `Settled Amount` back to `Activity to Service Line
Apportionment`.

### Configuration

Same pattern as Pool to Pool Config but in `Activity to Activity Config`:

| Column | Meaning |
| --- | --- |
| Active | 1 = this A→A pair participates |
| Driver Value | Raw volume for normalisation |
| Redistribution Percentage | % of activity costs that flow to other activities |
| Base Amount / Final Balance | Written back by Python ETL |

### Algorithm

Identical to Stage 1b — substitute `Activity` for `Cost Pool` throughout.

---

## Stage 3 — Activity to Service Line

The final stage. Routes settled activity costs to service lines.

**Formula (Pigment):**

```
Apportioned Amount =
  Activity to Service Line Apportionment[Settled Amount]
  × LOOKUP(Activity Config[Activity to Service Line Basis], Activity, Service Line)
  / 100
```

**Configuration required per activity:**

- `Activity to Service Line Basis` — which driver type splits this activity's costs. Model assumption, manually maintained.
- `Driver Value` in `Activity Config` — raw volume at each Service Line/Driver intersection. **Loaded from CSV each period**, not entered manually.

---

## Direct costs

Accounts classified as `Direct` in Account Config bypass Stages 1, 2, and 3. They route
straight to Service Lines via `Direct Percentage Share` configured per account/cost centre.

These are added in the P&L Report block alongside the apportioned indirect costs, giving
the full service line cost picture.

```
Direct Amount = Account Amount × Direct Percentage Share / 100
  (where Apportionment Type = 'Direct')
```

---

## Validation gate

Before running the ETL, six validation checks confirm the configuration is complete. Results
are written to the `Apportionment Reconciliation` block at `(Period, Version, VAL00–VAL05)`.

| Check | What it validates | Failure |
| --- | --- | --- |
| VAL00 | All accounts have an Apportionment Type | FAIL — no account should be blank |
| VAL01 | All Indirect accounts have Driver % = 100 | FAIL — incomplete split |
| VAL02 | Active Pool→Pool pairs have Redistribution%, Driver, and Driver Values | FAIL |
| VAL03 | Pools with Driver Values have a Driver assigned, and that Driver has values | FAIL |
| VAL04 | Activities with A2A config (Redistribution% or Driver) have Driver Values | WARNING |
| VAL05 | Activities with Driver Values have a Driver assigned, and that Driver has values | FAIL |
| VAL06 | Date/time stamp — written when checks complete | PASS |

**FAIL** blocks the ETL run. **WARNING** allows it to proceed (interim numbers acceptable).
The `--force` flag overrides all gate checks.

In Pigment: surface these as a validation dashboard — conditional colour coding on the
Reconciliation block, or as a separate admin screen before users trigger a run.

---

## Reconciliation checks

Six end-to-end balance checks confirm every dollar in equals every dollar out at each stage.
These are **live formulas** in the Reconciliation block — they update whenever underlying
data changes.

| Check | Input | Output | Passes if |
| --- | --- | --- | --- |
| RC01 | GL Amount at overhead accounts | Apportioned Amount at Total Cost Pools | `ABS(In − Out) ≤ 0.01` |
| RC02 | Pool base amount vs final balance | Pool reciprocal balance | `ABS(In − Out) ≤ 0.01` |
| RC03 | Pool amount at Input activity | Apportioned Amount at Total Activities | `ABS(In − Out) ≤ 0.01` |
| RC04 | Activity base amount vs final balance | Activity reciprocal balance | `ABS(In − Out) ≤ 0.01` |
| RC05 | Activity amount at Input service line | Apportioned Amount at Total Service Lines | `ABS(In − Out) ≤ 0.01` |
| RC06 | GL Input total | Post-apportionment at Total Service Lines | `ABS(In − Out) ≤ 0.01` |

RC06 is the end-to-end check. If it passes, every dollar of GL overhead has been correctly
traced through to a service line — no leakage, no double-counting.

---

## Import flows

### GL Actuals

Load from source finance system (SQL, CSV, or API) into Account Config:

- `Amount` per Account / Cost Centre / Period / Version
- `Apportionment Type` — classify each account as Direct, Indirect, or Excluded

### Drivers (CSV import — all config blocks)

Driver Values are loaded from CSV files into **all four config blocks** each period. They are
not entered manually — they are sourced from operational systems (HR, facilities, finance) and
refreshed at the start of each apportionment run.

| Block | Driver Values sourced from |
| --- | --- |
| Pool Config | Operational systems — headcount from HR, floor area from facilities, etc. |
| Pool to Pool Config | Same operational driver data for pool-to-pool relationships |
| Activity Config | Operational systems — volumes that drive activity-to-service-line splits |
| Activity to Activity Config | Same operational driver data for activity-to-activity relationships |

Each CSV row: Pool (or Activity) / Driver / Destination / Period / Version / Value.

`Active` flag and `Redistribution Percentage` in the reciprocal config blocks are
**model assumptions** maintained manually (or loaded from a separate config CSV) — they
define the shape of the reciprocal network and change infrequently.

### Period range

Always driven by `Start Period` and `End Period` attributes on the Version element.
Never hardcode period lists. Loading and running for all periods in a version:

```python
periods = get_version_periods(tm1_or_pigment, version='Budget')
for period in periods:
    run_apportionment(period, version)
```

### ETL sequence per version

```bash
# 1. Load drivers from source
python3 etl/load_drivers.py --version Budget

# 2. Load GL
python3 etl/load_gl.py --version Budget

# 3. Run validation gate
python3 etl/val_checks.py --version Budget

# 4. Run reciprocal stages (writes Settled Amounts back to Pigment)
python3 etl/run_apportionment.py --version Budget
```

---

## Output and reporting

### CST P&L Report block

Combines all cost flows into a single service-line P&L view:

| Dimension | Includes |
| --- | --- |
| Service Line | SL01–SL08 |
| Account | Full chart of accounts |
| Cost Centre | All cost centres |
| Period | Monthly, with FY rollups |
| Version | Budget, Forecast, Actuals |
| Stage | Pre Apportionment / Post Apportionment |

Pre Apportionment = GL amount as loaded. Post Apportionment = fully allocated to service lines.

### Key reports

| Report | Description |
| --- | --- |
| Service Line P&L | Cost by service line — pre vs post apportionment comparison |
| Pool Bridge | Shows how pool balances change through Stage 1 → 1b |
| Activity Bridge | Shows how activity balances change through Stage 2 → 2b |
| Reconciliation Dashboard | RC01–RC06 + VAL00–VAL05 status grid with variance |
| Driver Analysis | Shows driver values and their effect on cost splits |

---

## Design decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Reciprocal solver | Python iteration, not matrix algebra | Simpler to debug; converges in ~11 steps; no dependency on NumPy solver |
| Convergence tolerance | 0.01 (1 cent) | Practical precision for financial reporting |
| Reciprocal stage engine | External Python writes back to Pigment | Pigment formulas cannot express circular/iterative calculation |
| Gate check | VAL checks before ETL, FAIL blocks run | Protects apportionment from incomplete or misconfigured data |
| Period range source | Version Start/End Period attributes | Single source of truth — no hardcoded period lists |
| Direct vs Indirect | Apportionment Type flag per account | Keeps direct costs visible in the same model without a separate cube |
| Input sentinel | Reserved element on all coded properties | Avoids extra single-value properties for scalar config values |
| Dest mirror properties | Separate Cost Pool Dest and Activity Dest | Required for reciprocal config — source and destination are both dimensions of the config block |
