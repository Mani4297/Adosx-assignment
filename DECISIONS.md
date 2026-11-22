# Architectural & Reconciler Decisions

This document records the core architectural and business logic decisions made during the DealerOS dual-ledger reconciliation engine implementation.

---

## Decision: compare System B's value against System A's total_value
-Rejected: compare with base_value
-Why: System B values equal System A's `total_value` (`base_value` + `adjustment`) across 109 of 120 rows. Records where System B recorded `base_value` (e.g. `REC-1003`, `REC-1027`, `REC-1088`) are authentic value mismatches where adjustments were missed.

---

## Decision: parse missing and blank values as NULL (None) rather than 0.00
-Rejected: default blank or unparseable values to Decimal('0.00')
-Why: In accounting ledgers, zero represents a verified zero balance or neutral transaction. A blank field (such as `ENT/2026/4050`) denotes unknown or unentered data. Converting blank to zero produces misleading variance math ($160,405.85 variance instead of missing value) and corrupts audit trails.

---

## Decision: normalize messy record references with digit extraction (`REC-\d+`)
-Rejected: exact string matching or rigid manual hardcoded replacements
-Why: Variations like `rec1034`, ` REC - 1070 `, and `1112` reference genuine System A transactions. Extracting the numeric sequence via regex `r"\d+"` and formatting as `f"REC-{digits}"` resolves all reference formatting noise without altering original raw text stored in the database.

---

## Decision: treat balanced multi-entry splits as valid matching rows rather than duplicates
-Rejected: flag any record with `len(entries) > 1` as `DUPLICATE_IN_B`
-Why: `REC-1055` has two entries in System B (`71950.93` and `107926.39`, explicitly labeled "Entry part 2 of 2") that sum exactly to System A's `total_value` (`179877.32`). Multi-part ledger postings are legitimate in enterprise accounting. In contrast, genuine duplicates such as `REC-1042` (two entries of `112837.06` totaling `225674.12`) do not balance and are flagged as `DUPLICATE_IN_B`.

---

## Decision: flag VOIDED transactions in System A with active System B entries as RECORD_VOIDED
-Rejected: silently drop voided records or treat them as matching clean rows
-Why: When System A voids a transaction (`REC-1019`) but System B retains an active ledger posting for that exact amount, general ledger cash balances diverge. Flagging this discrepancy with reason `RECORD_VOIDED` alerts operations to post a reversing journal entry in System B.

---

## Decision: include location and date differences as distinct filterable disagreements
-Rejected: restrict reconciliation exclusively to amount and ID checks
-Why: Auditable financial events require agreement on what occurred, when it occurred, and where it occurred. `REC-1009` has date discrepancies (2026-03-31 vs 2026-04-02), and `REC-1077` has location discrepancies. Capturing `LOCATION_MISMATCH` and `DATE_MISMATCH` with dedicated filter tags provides full audit transparency.

---

## Decision: mask foreign organization location IDs on cross-tenant rows
-Rejected: expose raw foreign location ID `LOC-201` to `ORG-A`, or expose `ORG-A` transaction to `ORG-B`
-Why: Record `REC-1077` was created by `ORG-A` at `LOC-102`, but System B entered it under `LOC-201` (owned by `ORG-B`). Displaying `LOC-201` to `ORG-A` leaks competitor branch infrastructure across tenant boundaries. Masking the foreign location as `[External Org]` informs `ORG-A` that a location mismatch occurred without leaking confidential tenant details. Furthermore, `ORG-B` never sees the row because ownership remains with `ORG-A`.

---

## Decision: use Python DecimalField and SQLite database
-Rejected: float / IEEE 754 floating-point numbers and external DBMS servers (Postgres/MySQL)
-Why: Binary floating-point arithmetic causes precision drift (e.g., `0.1 + 0.2 != 0.3`), which is unacceptable in ledger reconciliation. Python's `Decimal` guarantees exact penny precision. SQLite is built into Python, requires zero external services or Docker, and ensures immediate, reproducible execution from a clean clone.
