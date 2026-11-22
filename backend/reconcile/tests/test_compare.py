from decimal import Decimal
import pytest
from reconcile.compare import compare_records
from reconcile.importer import normalize_ref, parse_amount

LOC_ORG_MAP = {
    "LOC-101": "ORG-A",
    "LOC-102": "ORG-A",
    "LOC-103": "ORG-A",
    "LOC-201": "ORG-B",
    "LOC-202": "ORG-B",
}


def make_a_record(
    record_id="REC-1001",
    location_id="LOC-101",
    event_date="2026-03-01",
    total_value=Decimal("100.00"),
    base_value=Decimal("80.00"),
    adjustment=Decimal("20.00"),
    state="CONFIRMED",
    actor_id="USR-1",
):
    return {
        "record_id": record_id,
        "location_id": location_id,
        "event_date": event_date,
        "total_value": total_value,
        "base_value": base_value,
        "adjustment": adjustment,
        "state": state,
        "actor_id": actor_id,
    }


def make_b_entry(
    entry_id="ENT/2026/4001",
    record_ref="REC-1001",
    location_id="LOC-101",
    recorded_on="2026-03-01",
    value=Decimal("100.00"),
    label="Regular entry",
):
    return {
        "entry_id": entry_id,
        "record_ref": record_ref,
        "record_ref_raw": record_ref,
        "location_id": location_id,
        "recorded_on": recorded_on,
        "value": value,
        "value_raw": str(value) if value is not None else "",
        "label": label,
    }


def test_clean_row_produces_no_disagreement():
    """A perfectly matching pair produces no disagreements."""
    a = {"REC-1001": make_a_record("REC-1001")}
    b = [make_b_entry("ENT/1", "REC-1001")]
    assert compare_records(a, b, LOC_ORG_MAP) == []


def test_missing_in_b():
    """An A record with no matching B entry must be flagged as MISSING_IN_B."""
    a = {"REC-1015": make_a_record("REC-1015", total_value=Decimal("41095.33"))}
    b = []
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "MISSING_IN_B"
    assert results[0]["record_id"] == "REC-1015"
    assert results[0]["a_value"] == "41095.33"
    assert results[0]["b_value"] is None


def test_orphan_in_b():
    """A B entry pointing to an unknown A record must be flagged as ORPHAN_IN_B."""
    a = {}
    b = [make_b_entry("ENT/2026/4901", "REC-1999", "LOC-102", value=Decimal("41250.00"))]
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "ORPHAN_IN_B"
    assert results[0]["record_id"] == "REC-1999"
    assert results[0]["entry_id"] == "ENT/2026/4901"
    assert results[0]["b_value"] == "41250.00"
    assert results[0]["a_value"] is None
    # Tenant ownership for orphans comes from B's location (LOC-102 -> ORG-A)
    assert results[0]["org_id"] == "ORG-A"


def test_duplicate_in_b():
    """Duplicate B entries entered twice with the same amount (or sum != total) must be flagged."""
    a = {"REC-1042": make_a_record("REC-1042", total_value=Decimal("112837.06"))}
    b = [
        make_b_entry("ENT/4042", "REC-1042", value=Decimal("112837.06")),
        make_b_entry("ENT/4902", "REC-1042", value=Decimal("112837.06")),
    ]
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "DUPLICATE_IN_B"
    assert results[0]["record_id"] == "REC-1042"
    assert results[0]["b_value"] == "225674.12"
    assert results[0]["a_value"] == "112837.06"


def test_split_entries_that_add_up_are_not_flagged():
    """Split entries in B that sum exactly to A's total_value are NOT an error."""
    a = {"REC-1055": make_a_record("REC-1055", total_value=Decimal("179877.32"))}
    b = [
        make_b_entry("ENT/4055", "REC-1055", value=Decimal("71950.93"), label="Part 1"),
        make_b_entry("ENT/4903", "REC-1055", value=Decimal("107926.39"), label="Entry part 2 of 2"),
    ]
    assert compare_records(a, b, LOC_ORG_MAP) == []


def test_value_mismatch():
    """Different amounts between A's total_value and B's value must be flagged."""
    a = {"REC-1003": make_a_record("REC-1003", total_value=Decimal("121388.01"), base_value=Decimal("94834.38"))}
    # System B erroneously recorded base_value
    b = [make_b_entry("ENT/4003", "REC-1003", value=Decimal("94834.38"))]
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "VALUE_MISMATCH"
    assert results[0]["record_id"] == "REC-1003"
    assert results[0]["a_value"] == "121388.01"
    assert results[0]["b_value"] == "94834.38"


def test_blank_value_is_flagged_and_never_treated_as_zero():
    """A blank B value is flagged as VALUE_MISMATCH and not converted to Decimal(0)."""
    a = {"REC-1050": make_a_record("REC-1050", total_value=Decimal("160405.85"))}
    b = [make_b_entry("ENT/4050", "REC-1050", value=None)]
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "VALUE_MISMATCH"
    assert results[0]["b_value"] is None
    assert results[0]["a_value"] == "160405.85"


def test_messy_references_normalized():
    """Non-standard references ('rec1034', ' REC - 1070 ', '1112') normalize and match cleanly."""
    assert normalize_ref("rec1034") == "REC-1034"
    assert normalize_ref(" REC - 1070 ") == "REC-1070"
    assert normalize_ref("1112") == "REC-1112"

    a = {
        "REC-1034": make_a_record("REC-1034", total_value=Decimal("84939.99")),
        "REC-1070": make_a_record("REC-1070", total_value=Decimal("1608.95")),
        "REC-1112": make_a_record("REC-1112", total_value=Decimal("52028.74")),
    }
    b = [
        make_b_entry("ENT/4034", "rec1034", value=Decimal("84939.99")),
        make_b_entry("ENT/4070", " REC - 1070 ", value=Decimal("1608.95")),
        make_b_entry("ENT/4112", "1112", value=Decimal("52028.74")),
    ]
    assert compare_records(a, b, LOC_ORG_MAP) == []


def test_indian_format_amount_parsing():
    """Indian style commas e.g. 1,25,400.00 parse correctly to Decimal 125400.00."""
    assert parse_amount("1,25,400.00") == Decimal("125400.00")
    assert parse_amount("") is None
    assert parse_amount(None) is None


def test_voided_record():
    """A record in System A marked VOIDED with an active B entry is flagged as RECORD_VOIDED."""
    a = {"REC-1019": make_a_record("REC-1019", state="VOIDED", total_value=Decimal("57092.35"))}
    b = [make_b_entry("ENT/4019", "REC-1019", value=Decimal("57092.35"))]
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "RECORD_VOIDED"
    assert results[0]["record_id"] == "REC-1019"


def test_location_mismatch_and_cross_tenant_masking():
    """Different locations are flagged; cross-tenant locations are masked to prevent leak."""
    # REC-1077 is at LOC-102 (ORG-A) in A, but LOC-201 (ORG-B) in B
    a = {"REC-1077": make_a_record("REC-1077", location_id="LOC-102", total_value=Decimal("83361.40"))}
    b = [make_b_entry("ENT/4077", "REC-1077", location_id="LOC-201", value=Decimal("83361.40"))]

    # Query without org filter
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "LOCATION_MISMATCH"
    assert results[0]["location_a"] == "LOC-102"
    assert results[0]["location_b"] == "[External Org]"  # masked!
    assert "LOC-201" not in results[0]["location_b"]

    # Query for ORG-A -> present
    res_a = compare_records(a, b, LOC_ORG_MAP, target_org="ORG-A")
    assert len(res_a) == 1
    assert res_a[0]["location_b"] == "[External Org]"

    # Query for ORG-B -> NOT present (owned by ORG-A)
    res_b = compare_records(a, b, LOC_ORG_MAP, target_org="ORG-B")
    assert len(res_b) == 0


def test_date_mismatch():
    """Different dates between event_date and recorded_on are flagged as DATE_MISMATCH."""
    a = {"REC-1009": make_a_record("REC-1009", event_date="2026-03-31", total_value=Decimal("111699.30"))}
    b = [make_b_entry("ENT/4009", "REC-1009", recorded_on="2026-04-02", value=Decimal("111699.30"))]
    results = compare_records(a, b, LOC_ORG_MAP)
    assert len(results) == 1
    assert results[0]["reason"] == "DATE_MISMATCH"
    assert results[0]["a_date"] == "2026-03-31"
    assert results[0]["b_date"] == "2026-04-02"


def test_tenant_isolation_strict():
    """Assert that ORG-A cannot see ORG-B records and vice-versa."""
    a = {
        "REC-A": make_a_record("REC-A", location_id="LOC-101", total_value=Decimal("100.00")),
        "REC-B": make_a_record("REC-B", location_id="LOC-201", total_value=Decimal("200.00")),
    }
    b = []  # both missing

    res_a = compare_records(a, b, LOC_ORG_MAP, target_org="ORG-A")
    assert len(res_a) == 1
    assert res_a[0]["record_id"] == "REC-A"
    assert res_a[0]["org_id"] == "ORG-A"

    res_b = compare_records(a, b, LOC_ORG_MAP, target_org="ORG-B")
    assert len(res_b) == 1
    assert res_b[0]["record_id"] == "REC-B"
    assert res_b[0]["org_id"] == "ORG-B"
