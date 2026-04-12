# tm1_apportionment

## Introduction

Every organisation has costs that don't belong to just one department or service — the IT team supports everyone, Facilities maintains the whole building, Finance processes payroll for all staff. These are **shared costs**, and the challenge is deciding how much each service line or product should bear.

The traditional approach is simple step-down allocation — costs trickle down a fixed hierarchy, one level at a time. It's fast, but it ignores a fundamental reality: **shared services support each other**. IT supports Finance. Finance supports HR. HR supports IT. In step-down, those circular relationships are ignored or approximated.

This module implements **Activity Based Costing (ABC)** with full reciprocal apportionment. Instead of a one-way waterfall, costs flow through a network of **Cost Pools** and **Activities** — and that network can have feedback loops. The engine keeps redistributing costs around the network until every loop has settled and the numbers stop changing. The result is a mathematically exact answer, not an approximation.

The mathematics behind this is the **Leontief Input-Output model** — the same framework used in macroeconomic analysis to model how industries depend on each other. Applied here, it means:

- A Facilities pool can apportion costs to IT, and IT can apportion costs back to Facilities
- Those circular flows are fully resolved, not ignored
- Every dollar of overhead is traced to the service line that ultimately consumed it
- The whole system balances end-to-end — what goes in must equal what comes out

The engine is built entirely inside **IBM Planning Analytics (TM1)**. Live apportionment calculations run as TM1 rules — they recalculate instantly whenever data changes. The reciprocal stages (where the circular flows are resolved) run as Python iteration, converging in around 11 steps. A full suite of validation and reconciliation checks confirms the model is balanced before and after every run.

Everything — dimensions, cubes, rules, views, processes — is defined as code in this repository and deployed to TM1 by the build scripts. There is no manual Architect work. A developer can clone this repo, point it at a TM1 server, and have a working model running in minutes.

---

## Architecture

The module has two distinct layers:

**Model Builder** — run once to build the TM1 model

Deploys all TM1 objects from source files in this repo — dimensions, cubes, rules, views, and TI processes. Nothing needs to be done manually in Architect. Git is the source of truth; a `git diff` shows exactly what changed between environments.

**App (ETL)** — run each period to load data and execute apportionment

Loads GL data and driver assumptions from SQL into TM1, runs the reciprocal iteration stages, validates data quality via gate checks, and reports reconciliation results end-to-end.

---

## Apportionment Stages

```text
Account → Pool          Stage 1   (TM1 rules, live)
Pool    → Pool          Stage 1b  (Python iteration — reciprocal)
Pool    → Activity      Stage 2   (TM1 rules, live)
Activity → Activity     Stage 2b  (Python iteration — reciprocal)
Activity → Service Line Stage 3   (TM1 rules, live)
```

---

## Prerequisites

- IBM Planning Analytics V12 server running and accessible
- Python 3.10+
- TM1py (see `requirements.txt`)

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/JDLovering/tm1_apportionment.git
cd tm1_apportionment
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.py config.py
```

Edit `config.py` with your TM1 server address, credentials, and account hierarchy consolidation names. See `config.example.py` for all options.

### 3. Build the model

```bash
python3 model_builder/build_cst_model.py
```

This builds everything on the TM1 server in one run — GBL dimensions, CST dimensions, all 10 cubes, rules, views, and TI processes.

### 4. Generate test data

The SQLite test database is not stored in git (binary file excluded). Generate it locally first:

```bash
python3 model_builder/create_test_db.py
```

This creates `tests/data/cst_test_data.db` — a fully populated test database covering Budget FY2027 (April 2026 → March 2027) with GL amounts, driver values, pool and activity config, and cost centre assignments across all 18 tables.

### 5. Load test data and run

```bash
python3 etl/load_gl.py --version Budget
python3 etl/load_drivers.py --version Budget
python3 etl/run_apportionment.py --version Budget
```

### 6. Start the ETL poller

Required for TI-triggered ETL from PAW.

```bash
./start_poller.sh
```

---

## Rebuild / Clean

```bash
python3 model_builder/cleanup_cst_model.py   # safely removes all CST objects
python3 model_builder/build_cst_model.py     # full rebuild
```

---

## Naming Conventions

The model uses `GBL`-prefixed shared dimensions (`GBL Period`, `GBL Version`, `GBL Account`, `GBL Cost Centre`) and `CST`-prefixed module dimensions. If your environment uses different dimension names, update the references in `config.py` and `model_builder/create_cst_cubes.py` before building.

The account hierarchy consolidation names (`TOTAL OVERHEAD`, `TOTAL DIRECT COSTS`) are configured in `config.py` and substituted into rules and views at deploy time — no hardcoding.

---

## Directory Structure

```text
tm1_apportionment/
├── config.example.py          ← copy to config.py and edit
├── model_builder/             ← builds all TM1 objects from source
│   ├── build_cst_model.py     ← orchestrator — run this to build
│   ├── cleanup_cst_model.py   ← safe teardown
│   ├── create_gbl_*.py        ← GBL dimension builders
│   └── create_cst_*.py        ← CST dimension and cube builders
├── rules/                     ← TM1 rule files (YAML source of truth)
├── views/                     ← TM1 view definitions (YAML)
├── ti_processes/              ← TI process definitions (YAML)
├── etl/                       ← ETL scripts and poller
│   ├── load_gl.py
│   ├── load_drivers.py
│   ├── run_apportionment.py
│   └── poller.py
└── tests/                     ← SQLite test database and loaders
```

---

## Documentation

Full technical documentation — TM1py rules, cube design, apportionment mathematics, ETL pipeline, reconciliation checks, design decisions — is in [CLAUDE.md](CLAUDE.md).

# CST Apportionment Flow

```mermaid
flowchart LR

    subgraph GL["GL Source"]
        ACC["GBL Account\n(6xxx Overhead\n5xxx Direct)"]
    end

    subgraph CFG["Config Cubes"]
        ACCCFG["CST Account Config\n(Amount, Type,\nDriver %, Direct %)"]
        POOLCFG["CST Pool Config\n(Driver % Share)"]
        ACTCFG["CST Activity Config\n(Input Volume,\nDriver % Share)"]
        P2PCFG["CST Pool to Pool Config\n(Driver Value)"]
        A2ACFG["CST Activity to Activity Config\n(Driver Value)"]
    end

    subgraph STAGE1["Stage 1 — Account → Pool"]
        A2P["CST Account to\nPool Apportionment\n(TM1 Rules)"]
    end

    subgraph STAGE1B["Stage 1b — Pool → Pool"]
        P2P["Python Solver\n(Reciprocal)"]
        P2A_SA["P2A Settled Amount"]
    end

    subgraph STAGE2["Stage 2 — Pool → Activity"]
        P2A["CST Pool to\nActivity Apportionment\n(TM1 Rules)"]
    end

    subgraph STAGE2B["Stage 2b — Activity → Activity"]
        A2A["Python Solver\n(Reciprocal)"]
        A2SL_SA["A2SL Settled Amount"]
    end

    subgraph STAGE3["Stage 3 — Activity → Service Line"]
        A2SL["CST Activity to\nService Line Apportionment\n(TM1 Rules)"]
    end

    subgraph OUTPUT["Output"]
        PL["CST Profit and\nLoss Report"]
        RECON["CST Apportionment\nReconciliation\nRC01-RC06 + VAL01-VAL06"]
    end

    ACC --> ACCCFG
    ACCCFG -->|Amount + Driver %| A2P
    POOLCFG -->|Driver % Share| P2A
    ACTCFG -->|Driver % Share| A2SL
    P2PCFG -->|Driver Values| P2P
    A2ACFG -->|Driver Values| A2A

    A2P -->|Apportioned Amount| P2P
    P2P -->|Settled Amount| P2A_SA
    P2A_SA --> P2A
    P2A -->|Apportioned Amount| A2A
    A2A -->|Settled Amount| A2SL_SA
    A2SL_SA --> A2SL
    A2SL -->|Apportioned Amount| PL

    A2P -.->|RC01| RECON
    P2P -.->|RC02| RECON
    P2A -.->|RC03| RECON
    A2A -.->|RC04| RECON
    A2SL -.->|RC05| RECON
    PL -.->|RC06| RECON
