# Test Data — cst_test_data.db

SQLite database providing sample data for the CST Apportionment module.
All codes align exactly with the live TM1 model.

Rebuild at any time:
```
python3 model_builder/create_test_db.py
```

---

## Tables

### gl_accounts
Master list of all GBL Account codes used in the TM1 model.

| Column | Type | Notes |
|--------|------|-------|
| account_code | TEXT PK | Matches GBL Account element names (4001–7009) |
| account_desc | TEXT | Full description |
| account_type | TEXT | Revenue / Direct Costs / Overhead / Allocated Overhead |
| cost_pool | TEXT | CST Cost Pool code this account feeds into — NULL if not applicable |

`cost_pool` is populated for 6000-series overhead accounts only. It records
which cost pool accumulates that account's spend before apportionment.

### cost_pools
| Column | Type | Notes |
|--------|------|-------|
| pool_code | TEXT PK | CP01–CP09, matches CST Cost Pool element names |
| pool_desc | TEXT | Full description |

### activities
| Column | Type | Notes |
|--------|------|-------|
| activity_code | TEXT PK | A01–A11, matches CST Activity element names |
| activity_desc | TEXT | Full description |

### service_lines
| Column | Type | Notes |
|--------|------|-------|
| service_line_code | TEXT PK | SL01–SL08, matches CST Service Line element names |
| service_line_desc | TEXT | Full description |

### pool_drivers
Cost pool to activity apportionment drivers.

| Column | Type | Notes |
|--------|------|-------|
| pool_code | TEXT PK | FK → cost_pools |
| activity_code | TEXT PK | FK → activities |
| driver_value | REAL | Raw driver quantity (e.g. square metres, FTE, tray count) |
| driver_percentage_share | REAL | `driver_value / pool_total * 100` — **sums to 100.00 per pool_code** |

Each cost pool (CP01–CP09) has one row per activity (A01–A11) = 99 rows total.

Driver basis by pool:

| Pool | Basis |
|------|-------|
| CP01 Facilities | Space / bed-days |
| CP02 Clinical Engineering | Equipment hours |
| CP03 Information Technology | System transactions |
| CP04 Human Resources | Headcount |
| CP05 Finance and Admin | Invoice / transaction count |
| CP06 Sterilisation | Tray count |
| CP07 Patient Transport | Patient moves |
| CP08 Catering | Meal count |
| CP09 Executive and Governance | FTE |

### activity_drivers
Activity to service line apportionment drivers.

| Column | Type | Notes |
|--------|------|-------|
| activity_code | TEXT PK | FK → activities |
| service_line_code | TEXT PK | FK → service_lines |
| driver_value | REAL | Raw driver quantity (encounters / procedures) |
| driver_percentage_share | REAL | **Sums to 100.00 per activity_code** |

Each activity (A01–A11) has one row per service line (SL01–SL08) = 88 rows total.

### gl_input
Monthly actuals and budget for all account/department combinations.

| Column | Type | Notes |
|--------|------|-------|
| period | TEXT PK | TM1 period name e.g. `Apr FY2025` |
| version | TEXT PK | `Actual` or `Budget` |
| account_code | TEXT PK | FK → gl_accounts |
| department_code | TEXT PK | GBL Department element name e.g. `D001` |
| amount | REAL | Amount in $000s |

Periods covered: **Apr FY2025, May FY2025, Jun FY2025**
Versions: **Actual** (all accounts), **Budget** (revenue only)

Department mapping:

| Range | Purpose |
|-------|---------|
| D001–D008 | Clinical departments — revenue and direct costs |
| D009 | Clinical Support — catering and nursing overhead |
| D010 | Medical Administration — executive and governance overhead |
| D011 | Facilities — building and property overhead |
| D012 | Clinical Engineering — equipment overhead |
| D013 | Information Technology — IT overhead |
| D014 | Human Resources — HR overhead |
| D015 | Finance and Administration — finance overhead |
| D016 | Sterilisation — sterilisation overhead |
| D017 | Patient Transport — orderly and transport overhead |

---

## Percentage integrity

Verified on every rebuild:

```sql
-- Must all equal 100.00
SELECT pool_code, ROUND(SUM(driver_percentage_share), 2)
FROM pool_drivers GROUP BY pool_code;

SELECT activity_code, ROUND(SUM(driver_percentage_share), 2)
FROM activity_drivers GROUP BY activity_code;
```
