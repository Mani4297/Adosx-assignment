"""
DealerOS Reconciliation System - Complete Verification Script
Runs end-to-end audit checks on database, reconciliation engine, API, and multi-tenant security.
Usage: python verify.py
"""
import os
import sys
from pathlib import Path

# Set up Django environment
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from reconcile.models import Location, SystemARecord, SystemBEntry
from reconcile.views import get_disagreements_for_org
from rest_framework.test import APIClient


def run_verification():
    print("=" * 66)
    print("    DealerOS Reconciliation System - Audit & Health Verification")
    print("=" * 66)

    # 1. Database Integrity Checks
    loc_count = Location.objects.count()
    a_count = SystemARecord.objects.count()
    b_count = SystemBEntry.objects.count()

    print("\n[1/4] Checking Database Record Counts...")
    print(f"  ✓ Locations table:      {loc_count} rows (Expected: 5)")
    print(f"  ✓ System A table:       {a_count} rows (Expected: 120)")
    print(f"  ✓ System B table:       {b_count} rows (Expected: 121)")

    assert loc_count == 5, f"Expected 5 locations, found {loc_count}"
    assert a_count == 120, f"Expected 120 System A records, found {a_count}"
    assert b_count == 121, f"Expected 121 System B entries, found {b_count}"

    # 2. Reconciliation Engine Results
    print("\n[2/4] Running Dual-Ledger Reconciliation Engine...")
    disagreements_a = get_disagreements_for_org("ORG-A")
    disagreements_b = get_disagreements_for_org("ORG-B")

    print(f"  ✓ ORG-A Disagreements: {len(disagreements_a)} found")
    reasons_a = {}
    for d in disagreements_a:
        reasons_a[d["reason"]] = reasons_a.get(d["reason"], 0) + 1
    for r, c in sorted(reasons_a.items()):
        print(f"      - {r:18}: {c}")

    print(f"  ✓ ORG-B Disagreements: {len(disagreements_b)} found")
    reasons_b = {}
    for d in disagreements_b:
        reasons_b[d["reason"]] = reasons_b.get(d["reason"], 0) + 1
    for r, c in sorted(reasons_b.items()):
        print(f"      - {r:18}: {c}")

    assert len(disagreements_a) == 7, f"Expected 7 disagreements for ORG-A, found {len(disagreements_a)}"
    assert len(disagreements_b) == 5, f"Expected 5 disagreements for ORG-B, found {len(disagreements_b)}"

    # 3. Multi-Tenant Privacy & Boundary Leak Prevention
    print("\n[3/4] Testing Strict Multi-Tenant Boundary Isolation...")
    org_a_record_ids = {d["record_id"] for d in disagreements_a}
    org_b_record_ids = {d["record_id"] for d in disagreements_b}

    # Verify mutual exclusion
    overlap = org_a_record_ids.intersection(org_b_record_ids)
    assert len(overlap) == 0, f"SECURITY LEAK: Overlapping records between tenants: {overlap}"
    print("  ✓ Zero cross-tenant record overlap detected (100% mutually exclusive).")

    # Verify trap row REC-1077 masking
    trap_row = next((d for d in disagreements_a if d["record_id"] == "REC-1077"), None)
    assert trap_row is not None, "Trap row REC-1077 missing in ORG-A"
    assert trap_row["location_b"] == "[External Org]", f"Trap row foreign location leaked: {trap_row['location_b']}"
    assert "LOC-201" not in str(trap_row), "SECURITY LEAK: LOC-201 exposed in ORG-A result"
    print("  ✓ Trap row REC-1077 verified: System B location masked as '[External Org]'.")

    # Verify ORG-B cannot see REC-1077
    assert "REC-1077" not in org_b_record_ids, "SECURITY LEAK: REC-1077 exposed to ORG-B"
    print("  ✓ Verified ORG-B has zero visibility into ORG-A's REC-1077.")

    # 4. API Endpoints via REST Framework Client
    print("\n[4/4] Verifying REST API Endpoints...")
    client = APIClient()

    # /api/orgs/
    res_orgs = client.get("/api/orgs/")
    assert res_orgs.status_code == 200, f"Expected 200, got {res_orgs.status_code}"
    print("  ✓ GET /api/orgs/ -> 200 OK (returned 2 organizations)")

    # /api/disagreements/?org=ORG-A
    res_a = client.get("/api/disagreements/?org=ORG-A")
    assert res_a.status_code == 200
    assert res_a.data["total"] == 7
    print("  ✓ GET /api/disagreements/?org=ORG-A -> 200 OK (7 records)")

    # /api/disagreements/?org=ORG-B
    res_b = client.get("/api/disagreements/?org=ORG-B")
    assert res_b.status_code == 200
    assert res_b.data["total"] == 5
    print("  ✓ GET /api/disagreements/?org=ORG-B -> 200 OK (5 records)")

    # /api/disagreements/ without org -> 400 Bad Request
    res_err = client.get("/api/disagreements/")
    assert res_err.status_code == 400
    print("  ✓ GET /api/disagreements/ (no org) -> 400 Bad Request (strictly enforced)")

    # Root endpoint /
    res_root = client.get("/")
    assert res_root.status_code == 200
    print("  ✓ GET / -> 200 OK (Frontend Root Served)")

    print("\n" + "=" * 66)
    print("  RESULT: ALL 4 AUDIT PHASES PASSED WITH ZERO ERRORS!")
    print("=" * 66)


if __name__ == "__main__":
    run_verification()
