# DealerOS — Multi-Tenant Dual-Ledger Reconciliation

A robust, multi-tenant dual-ledger reconciliation web application built with **Django REST Framework** and **React (Vite)**. It audits and reconciles transactional data recorded across two disparate enterprise software systems (**System A** and **System B**) across physical dealership locations, identifying and isolating all discrepancies without ever leaking confidential information across organizational tenant boundaries.

---

## What Was Built

- **Idempotent Data Ingestion Pipeline**: Ingests `locations.csv` (5 branches), `system_a.csv` (120 records), and `system_b.csv` (121 entries) into SQLite. Survives dirty formats, extracts noisy record references, handles Indian-style number grouping, and stores unparseable values as `NULL` without crashing or dropping rows.
- **Pure Reconciliation Engine (`compare.py`)**: Mathematically compares System A's `total_value` (`base_value` + `adjustment`) with System B's values. Detects:
  - `MISSING_IN_B`: Transactions in System A missing from System B.
  - `ORPHAN_IN_B`: System B entries pointing to non-existent System A records.
  - `DUPLICATE_IN_B`: Over-allocated or duplicated postings in System B.
  - `VALUE_MISMATCH`: Penny differences and missing/unparseable values.
  - `RECORD_VOIDED`: System A cancellations that remain active in System B.
  - `LOCATION_MISMATCH`: Discrepant dealership branch assignments.
  - `DATE_MISMATCH`: Calendar discrepancies between event dates and posting dates.
  - *Identifies legitimate multi-part splits (e.g. `REC-1055`) and avoids false-positive duplicate flags.*
- **Zero-Leak Multi-Tenant API (`views.py`)**: Enforces tenant scoping strictly at the database query level via `?org=ORG-A`. Protects cross-tenant privacy on trap rows (`REC-1077`) by masking foreign location IDs as `[External Org]`.
- **Interactive Audit Dashboard (React)**: Real-time tenant switcher, dynamic KPI counters, reason filtering, search, and sortable financial tables.
- **26 Comprehensive Unit & Integration Tests**: 100% test pass rate covering every disagreement reason, dirty edge cases, and cross-tenant leakage barriers.

---

## What Was Deliberately Not Built

To stay within the assessment scope and focus on correctness, data integrity, and strict tenant boundaries:
- **No User Authentication / SSO**: Multi-tenancy is demonstrated via the explicit `?org=` query parameter and tenant switcher rather than login sessions.
- **No Heavy External DBMS (PostgreSQL/MySQL) or Docker**: Uses Python's built-in SQLite for zero-friction setup and immediate reproducibility from a clean git clone.
- **No Server-Side Pagination**: With ~120 rows per system, client-side rendering with database-level tenant filtering provides instantaneous performance without pagination overhead.
- **No Write-Back / Editing System**: The reconciliation view is an audit and inspection tool; modifying historical ledger files was intentionally excluded.
- **No Heavy Component Libraries**: Built with vanilla modern CSS custom properties and standard HTML tables for maximum speed, clarity, and zero dependency risk.

---

## How to Run From a Clean Clone

### Prerequisites
- Python 3.11+ (tested on Python 3.12)
- Node.js 18+ (tested on Node v22)
- Git

### 1. Clone & Set Up Backend
```bash
git clone https://github.com/Mani4297/Adosx-assignment.git dealeros
cd dealeros

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt

# Run database migrations
cd backend
python manage.py migrate

# Ingest all CSV data (idempotent - safe to run multiple times)
python manage.py import_data

# Run all 26 backend & tenant isolation tests
pytest -v
```

### 2. Start the Backend API Server
```bash
# From dealeros/backend (with .venv active):
python manage.py runserver 8000
```
Backend API will be available at: `http://127.0.0.1:8000/api/disagreements/?org=ORG-A`

### 3. Start the Frontend Application
Open a new terminal window:
```bash
cd dealeros/frontend
npm install
npm run dev
```
Open your browser to: `http://localhost:5173`

*(Alternatively, to run everything with a single command without keeping a Node dev server open: run `npm run build` once in `frontend`, then `python manage.py runserver 8000` serves the built React app directly at `http://127.0.0.1:8000/`.)*

---

## How I Worked With the AI Agent

- **Tool & Agent**: Antigravity with Gemini 3.8 Flash.
- **Delegation Strategy**: I broke down the assessment into isolated, verifiable milestones following the step-by-step plan:
  1. Automated pre-import data discovery script to catalog all anomalies (`inspect_data.py`).
  2. Django data models with `DecimalField` and null-safe attributes.
  3. Safe CSV ingestion command with strict idempotency and audit counters.
  4. Pure comparison algorithm decoupled from web frameworks.
  5. Isolated API endpoints and React UI with real-time tenant switching.
  6. Comprehensive test suite verifying all 7 discrepancy conditions and cross-tenant leakage.
- **Verification Method**: I never accepted an AI assertion at face value. For every generated module, I executed automated verification scripts:
  - Checked exact row counts before and after database imports (120 A rows, 121 B entries).
  - Executed tests using `pytest -v` to ensure every failure condition triggers as expected.
  - Ran network request audits against `/api/disagreements/?org=ORG-A` to verify zero occurrence of `LOC-201` or `LOC-202`.

---

## The Three Assessment Questions

### a. One thing the AI agent got wrong. How did you notice?
During the initial unit testing phase for the API endpoint, the agent authored test fixtures using arbitrary alphanumeric IDs such as `REC-A1` and `REC-A2`. However, our reference normalizer function `normalize_ref(raw)` uses `re.search(r"\d+", raw)` to extract numeric sequences, which turned `REC-A1` into `REC-1`. Because `REC-1` did not match the test record's key `REC-A1`, the comparison engine flagged the row as `MISSING_IN_B` and created a false `ORPHAN_IN_B`, causing two assertions in `test_api.py` to fail. I caught this immediately when running `pytest -v`. I verified the actual datasets, confirmed that DealerOS records strictly use numeric identifiers (`REC-1001` through `REC-1120`), and updated the test fixtures to use realistic `REC-1001` patterns, resulting in all tests passing cleanly.

### b. The part you are least confident about, and why
The part I am least confident about is the one-sided visibility choice for the cross-tenant location mismatch (`REC-1077`). In this implementation, `REC-1077` was created by `ORG-A` at branch `LOC-102`, but System B entered it under `LOC-201` (owned by `ORG-B`). Following the prompt's recommendation, we assigned ownership strictly to `ORG-A` (the originating creator in System A) and masked System B's foreign location as `[External Org]`, while completely hiding the row from `ORG-B`. While this guarantees zero data leakage to `ORG-B`, in a real accounting audit `ORG-B`'s branch manager at `LOC-201` might see an unexplained balance in System B with no matching source document in System A. Determining whether `ORG-B` should receive a blinded notification ("An unauthorized booking referenced your location") requires operational guidance from the finance controller.

### c. If you had a second day, what would you fix first?
If I had a second day, I would build an **Interactive Resolution & Audit Workflow**. When an auditor reviews a discrepancy (such as a split like `REC-1055` or a value mismatch like `REC-1003`), they should be able to:
1. Attach an audit note explaining the root cause (e.g., "Confirmed base value entered in error; adjustment voucher #442 issued").
2. Mark the status as "Resolved" or "Pending Adjustment Entry".
3. Export an official PDF/CSV Reconciliation Certificate signed with timestamps for external audit compliance.
