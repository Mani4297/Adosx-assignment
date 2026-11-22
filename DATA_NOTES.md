# Dataset Analysis & Discovery Notes

Initial manual and scripted audit of the three datasets (`locations.csv`, `system_a.csv`, `system_b.csv`).

## 1. File Summary
- `locations.csv`: 5 rows.
  - Mapping: `LOC-101`, `LOC-102`, `LOC-103` belong to `ORG-A`.
  - Mapping: `LOC-201`, `LOC-202` belong to `ORG-B`.
  - Rule: This file is the single source of truth for organization ownership. Never infer org ID from location ID pattern.
- `system_a.csv`: 120 rows.
  - Columns: `record_id`, `location_id`, `event_date`, `category_code`, `actor_id`, `base_value`, `adjustment`, `total_value`, `state`.
  - States present: `CONFIRMED` (119 records), `VOIDED` (1 record: `REC-1019`).
  - Blank values: `REC-1050` has an empty `actor_id` (`CAT-03,,125317.07`). Must be preserved as null, not dropped.
  - Financial values: `total_value = base_value + adjustment`. All comparisons against System B must use `total_value`.
- `system_b.csv`: 121 rows.
  - Columns: `entry_id`, `record_ref`, `location_id`, `recorded_on`, `value`, `label`.
  - Extra row count: 121 entries vs 120 in System A.

## 2. Dirty Data Patterns Discovered

### A. Non-Standard Reference Formats (Require Normalization)
- `ENT/2026/4034`: `rec1034` -> Lowercase, no hyphen. Resolves to `REC-1034`.
- `ENT/2026/4070`: ` REC - 1070 ` -> Extra spaces around hyphen and padding. Resolves to `REC-1070`.
- `ENT/2026/4112`: `1112` -> Digits only without prefix. Resolves to `REC-1112`.
*All three represent valid matching records once normalized using regex `r"\d+"`.*

### B. Number Formatting and Blank Values
- `ENT/2026/4050`: `value` is empty string (`""`). Must parse to `None` / `NULL`, NEVER zero. Flagged as `VALUE_MISMATCH` because comparison cannot be verified.
- `ENT/2026/4064`: `value` is formatted with Indian-style grouping commas: `"1,25,400.00"`. Must parse cleanly to `Decimal('125400.00')` without crashing. Its numeric value differs from System A's total (`183244.16`), so it flags as `VALUE_MISMATCH`.

### C. Missing and Orphan Records
- Missing in System B:
  - `REC-1015` (`LOC-103`, `ORG-A`): In System A, but completely absent from System B. Reason: `MISSING_IN_B`.
  - `REC-1061` (`LOC-202`, `ORG-B`): In System A, but completely absent from System B. Reason: `MISSING_IN_B`.
- Orphan in System B:
  - `ENT/2026/4901`: Points to `REC-1999` at `LOC-102` (`ORG-A`), value `41250.00`. `REC-1999` does not exist in System A. Reason: `ORPHAN_IN_B`. Tenant ownership determined by entry's own `location_id`.

### D. Duplicates vs. Splits
- Duplicate:
  - `REC-1042` (`LOC-101`, `ORG-A`): System A total = `112837.06`. System B has two entries: `ENT/2026/4042` (`112837.06`) and `ENT/2026/4902` (`112837.06`). Sum = `225674.12` != `112837.06`. Both labeled "Entry for CAT-02". Reason: `DUPLICATE_IN_B`.
- Valid Split (Not an Error):
  - `REC-1055` (`LOC-103`, `ORG-A`): System A total = `179877.32`. System B has `ENT/2026/4055` (`71950.93`) and `ENT/2026/4903` (`107926.39`, labeled "Entry part 2 of 2"). `71950.93 + 107926.39 = 179877.32`. Exactly equals System A `total_value`. This is a legitimate multi-entry split and must NOT be flagged as an error.

### E. Value Mismatches (Base vs. Total Trap)
- `REC-1003` (`LOC-202`, `ORG-B`): A total `121388.01`, B val `94834.38`. (Note: System B entered System A's `base_value`).
- `REC-1027` (`LOC-102`, `ORG-A`): A total `79259.03`, B val `61921.12`. (System B entered `base_value`).
- `REC-1088` (`LOC-103`, `ORG-A`): A total `138948.30`, B val `108553.36`. (System B entered `base_value`).
- `REC-1050`: B value blank.
- `REC-1064`: B val `125400.00` vs A total `183244.16`.

### F. Voided Records
- `REC-1019` (`LOC-202`, `ORG-B`): System A state is `VOIDED`, but System B has an active entry `ENT/2026/4019` for `57092.35`. Disagreement reason: `RECORD_VOIDED`.

### G. Cross-Tenant Location Trap Row
- `REC-1077`: System A records this event at `LOC-102` (`ORG-A`). System B recorded it under `LOC-201` (`ORG-B`).
- Danger: Directly exposing `LOC-201` in ORG-A's table leaks another organization's location ID across tenant boundaries.
- Strategy: Tenant ownership is governed by System A. When querying for `ORG-A`, show `LOCATION_MISMATCH`, show System A's `LOC-102`, and mask System B's location as `[External Org]`. `ORG-B` does not see this record.

### H. Date Mismatch
- `REC-1009` (`LOC-201`, `ORG-B`): System A `event_date` is `2026-03-31`, System B `recorded_on` is `2026-04-02`. Reason: `DATE_MISMATCH`.
