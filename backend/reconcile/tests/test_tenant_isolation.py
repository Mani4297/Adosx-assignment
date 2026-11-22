import pytest
from rest_framework.test import APIClient
from reconcile.models import Location, SystemARecord, SystemBEntry
from reconcile.importer import import_all_data


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def populated_db(db):
    """Seed full database using the CSV importer."""
    import_all_data()


def test_tenant_isolation_org_a_never_sees_org_b_data(api_client, populated_db):
    """
    Test that an ORG-A query:
    1. Returns exclusively ORG-A owned records.
    2. Contains no unmasked references to ORG-B locations (LOC-201, LOC-202).
    3. Handles the trap row REC-1077 without leaking LOC-201.
    4. Includes ORG-A orphans (ENT/2026/4901 at LOC-102).
    """
    response = api_client.get("/api/disagreements/?org=ORG-A")
    assert response.status_code == 200
    data = response.data
    assert data["org"] == "ORG-A"

    # Known ORG-B locations that must NEVER appear unmasked in ORG-A responses
    org_b_locations = {"LOC-201", "LOC-202"}
    org_b_records = set(
        SystemARecord.objects.filter(location__org_id="ORG-B").values_list("record_id", flat=True)
    )

    results = data["results"]
    assert len(results) > 0, "ORG-A must have disagreements flagged"

    found_trap_row = False
    found_orphan = False

    for row in results:
        rid = row["record_id"]
        loc = row["location"]
        loc_a = row["location_a"]
        loc_b = row["location_b"]

        # Ensure no ORG-B record is returned
        assert rid not in org_b_records, f"Security leak: ORG-B record {rid} returned to ORG-A"

        # Ensure System A location belongs to ORG-A
        if loc_a:
            assert loc_a in {"LOC-101", "LOC-102", "LOC-103"}

        # Ensure primary location belongs to ORG-A
        if loc:
            assert loc in {"LOC-101", "LOC-102", "LOC-103"}

        # Cross-Tenant Trap Row Check: REC-1077 has LOC-201 in System B
        if rid == "REC-1077":
            found_trap_row = True
            assert row["reason"] == "LOCATION_MISMATCH"
            assert loc_a == "LOC-102"
            # Crucial: LOC-201 MUST NOT be exposed!
            assert "LOC-201" not in str(loc_b), "Security leak: Foreign location LOC-201 exposed in location_b"
            assert loc_b == "[External Org]"

        # Orphan Check: ENT/2026/4901 at LOC-102 belongs to ORG-A
        if row["entry_id"] == "ENT/2026/4901":
            found_orphan = True
            assert row["reason"] == "ORPHAN_IN_B"
            assert loc == "LOC-102"

        # Check all string fields in the response for raw leakage of ORG-B locations
        for field in ("location", "location_a", "location_b"):
            val = row.get(field)
            if val:
                assert val not in org_b_locations, f"Security leak: {val} found in field '{field}' for ORG-A"

    assert found_trap_row, "Trap row REC-1077 should be reported to ORG-A with masked foreign location"
    assert found_orphan, "Orphan ENT/2026/4901 at LOC-102 should be reported to ORG-A"


def test_tenant_isolation_org_b_never_sees_org_a_data(api_client, populated_db):
    """
    Test that an ORG-B query:
    1. Returns exclusively ORG-B owned records.
    2. Contains no references to ORG-A locations (LOC-101, LOC-102, LOC-103).
    3. Never sees ORG-A's REC-1077 even though System B recorded LOC-201.
    4. Never sees ORG-A's orphan (ENT/2026/4901).
    """
    response = api_client.get("/api/disagreements/?org=ORG-B")
    assert response.status_code == 200
    data = response.data
    assert data["org"] == "ORG-B"

    org_a_locations = {"LOC-101", "LOC-102", "LOC-103"}
    org_a_records = set(
        SystemARecord.objects.filter(location__org_id="ORG-A").values_list("record_id", flat=True)
    )

    results = data["results"]
    assert len(results) > 0, "ORG-B must have disagreements flagged"

    for row in results:
        rid = row["record_id"]
        loc = row["location"]
        loc_a = row["location_a"]
        loc_b = row["location_b"]

        # Ensure no ORG-A record is returned
        assert rid not in org_a_records, f"Security leak: ORG-A record {rid} returned to ORG-B"
        assert rid != "REC-1077", "Security leak: ORG-A record REC-1077 returned to ORG-B"
        assert row.get("entry_id") != "ENT/2026/4901", "Security leak: ORG-A orphan returned to ORG-B"

        # Ensure locations belong to ORG-B
        if loc_a:
            assert loc_a in {"LOC-201", "LOC-202"}
        if loc:
            assert loc in {"LOC-201", "LOC-202"}

        for field in ("location", "location_a", "location_b"):
            val = row.get(field)
            if val:
                assert val not in org_a_locations, f"Security leak: {val} found in field '{field}' for ORG-B"


def test_cross_org_database_query_level_filtering(db, populated_db):
    """
    Verify that query-level isolation functions independently of view serialization.
    Directly query helper function get_disagreements_for_org.
    """
    from reconcile.views import get_disagreements_for_org

    disagreements_a = get_disagreements_for_org("ORG-A")
    disagreements_b = get_disagreements_for_org("ORG-B")

    rec_a = {d["record_id"] for d in disagreements_a}
    rec_b = {d["record_id"] for d in disagreements_b}

    # Mutual exclusion between tenant results
    intersection = rec_a.intersection(rec_b)
    assert len(intersection) == 0, f"Disagreements leaked across tenants: {intersection}"
