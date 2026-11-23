import pytest
from rest_framework.test import APIClient
from reconcile.models import Location, SystemARecord, SystemBEntry
from decimal import Decimal


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def setup_test_data(db):
    """Seed minimal multi-tenant dataset for API testing."""
    loc_a = Location.objects.create(location_id="LOC-101", org_id="ORG-A", location_name="Branch 101")
    loc_b = Location.objects.create(location_id="LOC-201", org_id="ORG-B", location_name="Branch 201")

    # Record in ORG-A with value mismatch
    SystemARecord.objects.create(
        record_id="REC-1001",
        location=loc_a,
        event_date="2026-03-01",
        category_code="CAT-01",
        base_value=Decimal("80.00"),
        adjustment=Decimal("20.00"),
        total_value=Decimal("100.00"),
        state="CONFIRMED",
    )
    SystemBEntry.objects.create(
        entry_id="ENT-4001",
        record_ref="REC-1001",
        record_ref_raw="REC-1001",
        location=loc_a,
        recorded_on="2026-03-01",
        value=Decimal("90.00"),
        value_raw="90.00",
        label="Entry 4001",
    )

    # Record in ORG-A that is missing in B
    SystemARecord.objects.create(
        record_id="REC-1002",
        location=loc_a,
        event_date="2026-03-02",
        category_code="CAT-01",
        base_value=Decimal("50.00"),
        adjustment=Decimal("0.00"),
        total_value=Decimal("50.00"),
        state="CONFIRMED",
    )

    # Record in ORG-B that is missing in B
    SystemARecord.objects.create(
        record_id="REC-2001",
        location=loc_b,
        event_date="2026-03-03",
        category_code="CAT-02",
        base_value=Decimal("200.00"),
        adjustment=Decimal("0.00"),
        total_value=Decimal("200.00"),
        state="CONFIRMED",
    )


def test_api_missing_org_parameter(api_client, db):
    """Calling /api/disagreements/ without ?org returns 400 Bad Request."""
    response = api_client.get("/api/disagreements/")
    assert response.status_code == 400
    assert "required" in response.data["error"].lower()


def test_api_invalid_org_parameter(api_client, setup_test_data):
    """Calling with unknown org returns 404."""
    response = api_client.get("/api/disagreements/?org=ORG-NONEXISTENT")
    assert response.status_code == 404


def test_api_org_a_returns_only_org_a_data(api_client, setup_test_data):
    """Querying for ORG-A returns its disagreements and none of ORG-B."""
    response = api_client.get("/api/disagreements/?org=ORG-A")
    assert response.status_code == 200
    data = response.data
    assert data["org"] == "ORG-A"
    assert data["total"] == 2
    record_ids = {r["record_id"] for r in data["results"]}
    assert record_ids == {"REC-1001", "REC-1002"}
    assert "REC-2001" not in record_ids


def test_api_org_b_returns_only_org_b_data(api_client, setup_test_data):
    """Querying for ORG-B returns its disagreements and none of ORG-A."""
    response = api_client.get("/api/disagreements/?org=ORG-B")
    assert response.status_code == 200
    data = response.data
    assert data["org"] == "ORG-B"
    assert data["total"] == 1
    assert data["results"][0]["record_id"] == "REC-2001"


def test_api_clean_match_metrics_and_include_clean(api_client, setup_test_data):
    """Clean rows contribute to summary metrics and are returned only when requested."""
    location = Location.objects.get(location_id="LOC-101")
    SystemARecord.objects.create(
        record_id="REC-1003",
        location=location,
        event_date="2026-03-04",
        category_code="CAT-01",
        base_value=Decimal("30.00"),
        adjustment=Decimal("0.00"),
        total_value=Decimal("30.00"),
        state="CONFIRMED",
    )
    SystemBEntry.objects.create(
        entry_id="ENT-4003",
        record_ref="REC-1003",
        record_ref_raw="REC-1003",
        location=location,
        recorded_on="2026-03-04",
        value=Decimal("30.00"),
        value_raw="30.00",
        label="Matching entry",
    )
    SystemARecord.objects.create(
        record_id="REC-1004",
        location=location,
        event_date="2026-03-05",
        category_code="CAT-01",
        base_value=Decimal("50.00"),
        adjustment=Decimal("0.00"),
        total_value=Decimal("50.00"),
        state="VOIDED",
    )
    for entry_id, value, recorded_on in (
        ("ENT-4004A", "20.00", "2026-03-05"),
        ("ENT-4004B", "30.00", "2026-03-06"),
    ):
        SystemBEntry.objects.create(
            entry_id=entry_id,
            record_ref="REC-1004",
            record_ref_raw="REC-1004",
            location=location,
            recorded_on=recorded_on,
            value=Decimal(value),
            value_raw=value,
            label="Split entry",
        )

    response = api_client.get("/api/disagreements/?org=ORG-A")
    assert response.status_code == 200
    assert response.data["total"] == 4
    assert response.data["total_disagreements"] == 3
    assert response.data["total_clean"] == 1
    assert response.data["total_analyzed"] == 4
    assert response.data["match_rate_pct"] == 25.0
    assert all(not row["reason"].startswith("CLEAN_") for row in response.data["results"])

    response_with_clean = api_client.get("/api/disagreements/?org=ORG-A&include_clean=true")
    assert response_with_clean.status_code == 200
    assert response_with_clean.data["total"] == 5
    assert any(row["reason"] == "CLEAN_MATCH" for row in response_with_clean.data["results"])


def test_api_reason_filter(api_client, setup_test_data):
    """Filtering by ?reason=MISSING_IN_B returns only that disagreement type."""
    response = api_client.get("/api/disagreements/?org=ORG-A&reason=MISSING_IN_B")
    assert response.status_code == 200
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["record_id"] == "REC-1002"
    assert response.data["results"][0]["reason"] == "MISSING_IN_B"


def test_api_sorting_by_value(api_client, setup_test_data):
    """Sorting by value works in both ascending and descending order."""
    res_desc = api_client.get("/api/disagreements/?org=ORG-A&sort=-value")
    assert res_desc.status_code == 200
    # REC-1001 has value 90.00, REC-1002 has A total 50.00
    assert res_desc.data["results"][0]["record_id"] == "REC-1001"

    res_asc = api_client.get("/api/disagreements/?org=ORG-A&sort=value")
    assert res_asc.status_code == 200
    assert res_asc.data["results"][0]["record_id"] == "REC-1002"


def test_api_orgs_endpoint(api_client, setup_test_data):
    """The /api/orgs/ endpoint lists all registered organizations and location counts."""
    response = api_client.get("/api/orgs/")
    assert response.status_code == 200
    org_ids = [item["org_id"] for item in response.data]
    assert "ORG-A" in org_ids
    assert "ORG-B" in org_ids


def test_root_endpoint_status_or_frontend(api_client):
    """The root / endpoint responds with 200 OK (serving built frontend or status JSON)."""
    response = api_client.get("/")
    assert response.status_code == 200
