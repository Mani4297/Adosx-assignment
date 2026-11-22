from decimal import Decimal
from typing import Any, Dict, List, Optional
from .importer import normalize_ref


def compare_records(
    a_records: Dict[str, Dict[str, Any]],
    b_entries: List[Dict[str, Any]],
    location_org_map: Optional[Dict[str, str]] = None,
    target_org: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Pure Python reconciliation engine comparing System A records against System B entries.
    Flags:
      - MISSING_IN_B: Record in A has no matching B entry.
      - ORPHAN_IN_B: Entry in B references a record that does not exist in A.
      - DUPLICATE_IN_B: Record in A has multiple B entries whose sum != A total_value.
        (Note: multi-entry splits whose sum == A total_value are NOT flagged).
      - VALUE_MISMATCH: Single B entry value != A total_value, or B value is None (blank).
      - RECORD_VOIDED: Record in A is VOIDED but has an active entry in B.
      - LOCATION_MISMATCH: A and B record different location IDs.
      - DATE_MISMATCH: A event_date differs from B recorded_on.

    Tenant isolation:
      - Rows are assigned org_id based on location_id via location_org_map (never from regex/ID pattern).
      - For cross-tenant location mismatches, if viewed by the owning org, the foreign location is masked.
      - If target_org is specified, only rows belonging to target_org are returned.
    """
    loc_map = location_org_map or {}
    disagreements = []

    # 1. Group B entries by normalized record reference
    b_by_ref: Dict[str, List[Dict[str, Any]]] = {}
    for entry in b_entries:
        raw_ref = entry.get("record_ref") or entry.get("record_ref_raw")
        clean_ref = normalize_ref(raw_ref)
        if clean_ref:
            b_by_ref.setdefault(clean_ref, []).append(entry)
        else:
            # Entry has no discernible reference at all
            b_by_ref.setdefault(f"INVALID-{entry.get('entry_id')}", []).append(entry)

    # 2. Identify ORPHAN_IN_B: B entries referencing records absent in A
    for ref, entries in b_by_ref.items():
        if ref not in a_records:
            for e in entries:
                b_loc = e.get("location_id")
                org = loc_map.get(b_loc)
                val = e.get("value")
                diff = str(val) if val is not None else None
                disagreements.append({
                    "reason": "ORPHAN_IN_B",
                    "record_id": ref,
                    "entry_id": e.get("entry_id"),
                    "location": b_loc,
                    "location_a": None,
                    "location_b": b_loc,
                    "a_value": None,
                    "b_value": str(val) if val is not None else None,
                    "difference": diff,
                    "a_date": None,
                    "b_date": str(e.get("recorded_on")) if e.get("recorded_on") else None,
                    "org_id": org,
                    "details": f"System B entry {e.get('entry_id')} references '{ref}', which does not exist in System A.",
                })

    # 3. Walk through each System A record
    for rid, a in a_records.items():
        a_loc = a.get("location_id")
        org = loc_map.get(a_loc)
        a_tot = a.get("total_value")
        a_date = str(a.get("event_date")) if a.get("event_date") else None
        state = a.get("state", "CONFIRMED")
        entries = b_by_ref.get(rid, [])

        # Case A: Missing in B
        if not entries:
            disagreements.append({
                "reason": "MISSING_IN_B",
                "record_id": rid,
                "entry_id": None,
                "location": a_loc,
                "location_a": a_loc,
                "location_b": None,
                "a_value": str(a_tot) if a_tot is not None else None,
                "b_value": None,
                "difference": f"-{a_tot}" if a_tot is not None else None,
                "a_date": a_date,
                "b_date": None,
                "org_id": org,
                "details": f"Record {rid} exists in System A but is missing in System B.",
            })
            continue

        # Case B: Multiple entries in B for this record
        if len(entries) > 1:
            vals = [e.get("value") for e in entries]
            entry_ids = ", ".join(e.get("entry_id", "") for e in entries)

            if any(v is None for v in vals):
                # At least one entry has a blank/invalid value
                disagreements.append({
                    "reason": "VALUE_MISMATCH",
                    "record_id": rid,
                    "entry_id": entry_ids,
                    "location": a_loc,
                    "location_a": a_loc,
                    "location_b": ", ".join(filter(None, [e.get("location_id") for e in entries])),
                    "a_value": str(a_tot) if a_tot is not None else None,
                    "b_value": None,
                    "difference": None,
                    "a_date": a_date,
                    "b_date": ", ".join(filter(None, [str(e.get("recorded_on")) for e in entries])),
                    "org_id": org,
                    "details": f"Record {rid} has multiple B entries, but at least one has an unparseable or blank value.",
                })
            else:
                total_b = sum(vals)
                if total_b != a_tot:
                    # Not a balanced split -> Real duplicate / amount mismatch
                    diff = total_b - a_tot
                    disagreements.append({
                        "reason": "DUPLICATE_IN_B",
                        "record_id": rid,
                        "entry_id": entry_ids,
                        "location": a_loc,
                        "location_a": a_loc,
                        "location_b": ", ".join(filter(None, [e.get("location_id") for e in entries])),
                        "a_value": str(a_tot) if a_tot is not None else None,
                        "b_value": str(total_b),
                        "difference": f"+{diff}" if diff > 0 else str(diff),
                        "a_date": a_date,
                        "b_date": ", ".join(filter(None, [str(e.get("recorded_on")) for e in entries])),
                        "org_id": org,
                        "details": f"Multiple System B entries sum to {total_b}, which differs from System A total {a_tot}.",
                    })
                # If total_b == a_tot, it is a valid split (e.g. REC-1055) -> Not an error!
            continue

        # Case C: Exactly one entry in B
        e = entries[0]
        b_val = e.get("value")
        b_loc = e.get("location_id")
        b_date = str(e.get("recorded_on")) if e.get("recorded_on") else None
        b_entry_id = e.get("entry_id")

        # 1. Check Value Mismatch
        if b_val is None:
            disagreements.append({
                "reason": "VALUE_MISMATCH",
                "record_id": rid,
                "entry_id": b_entry_id,
                "location": a_loc,
                "location_a": a_loc,
                "location_b": b_loc,
                "a_value": str(a_tot) if a_tot is not None else None,
                "b_value": None,
                "difference": None,
                "a_date": a_date,
                "b_date": b_date,
                "org_id": org,
                "details": f"System B value for {rid} is missing or blank.",
            })
        elif b_val != a_tot:
            diff = b_val - a_tot
            disagreements.append({
                "reason": "VALUE_MISMATCH",
                "record_id": rid,
                "entry_id": b_entry_id,
                "location": a_loc,
                "location_a": a_loc,
                "location_b": b_loc,
                "a_value": str(a_tot) if a_tot is not None else None,
                "b_value": str(b_val),
                "difference": f"+{diff}" if diff > 0 else str(diff),
                "a_date": a_date,
                "b_date": b_date,
                "org_id": org,
                "details": f"System B value {b_val} differs from System A total {a_tot}.",
            })

        # 2. Check Voided Record
        if state == "VOIDED":
            disagreements.append({
                "reason": "RECORD_VOIDED",
                "record_id": rid,
                "entry_id": b_entry_id,
                "location": a_loc,
                "location_a": a_loc,
                "location_b": b_loc,
                "a_value": str(a_tot) if a_tot is not None else None,
                "b_value": str(b_val) if b_val is not None else None,
                "difference": None,
                "a_date": a_date,
                "b_date": b_date,
                "org_id": org,
                "details": f"Record {rid} is VOIDED in System A, but System B retains an active entry.",
            })

        # 3. Check Location Mismatch (handling cross-tenant leak prevention)
        if b_loc and b_loc != a_loc:
            b_org = loc_map.get(b_loc)
            is_cross_org = (b_org != org)
            
            # Mask foreign location if viewed from a different org
            safe_b_loc = "[External Org]" if is_cross_org else b_loc

            disagreements.append({
                "reason": "LOCATION_MISMATCH",
                "record_id": rid,
                "entry_id": b_entry_id,
                "location": a_loc,
                "location_a": a_loc,
                "location_b": safe_b_loc,
                "a_value": str(a_tot) if a_tot is not None else None,
                "b_value": str(b_val) if b_val is not None else None,
                "difference": None,
                "a_date": a_date,
                "b_date": b_date,
                "org_id": org,
                "details": f"System A location is {a_loc}, while System B recorded {'an external organization location' if is_cross_org else b_loc}.",
            })

        # 4. Check Date Mismatch
        if b_date and a_date and b_date != a_date:
            disagreements.append({
                "reason": "DATE_MISMATCH",
                "record_id": rid,
                "entry_id": b_entry_id,
                "location": a_loc,
                "location_a": a_loc,
                "location_b": b_loc,
                "a_value": str(a_tot) if a_tot is not None else None,
                "b_value": str(b_val) if b_val is not None else None,
                "difference": None,
                "a_date": a_date,
                "b_date": b_date,
                "org_id": org,
                "details": f"System A event_date {a_date} differs from System B recorded_on {b_date}.",
            })

    # 4. Filter by target_org if requested (Strict Tenant Isolation)
    if target_org:
        disagreements = [d for d in disagreements if d.get("org_id") == target_org]

    return disagreements
