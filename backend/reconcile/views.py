from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List
from django.db import models
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .compare import compare_records
from .models import Location, SystemARecord, SystemBEntry


def get_disagreements_for_org(org_id: str) -> List[Dict[str, Any]]:
    """
    Fetches database records for the requested organization and runs reconciliation.
    Strict tenant boundary:
    1. System A records are queried strictly for the given org's locations.
    2. System B entries are queried for the given org's locations, OR matching the org's A record references.
       Entries referencing records owned by another org are NOT treated as orphans for this org.
    3. Location mapping is queried strictly from the Location table.
    """
    # 1. Map locations to organizations
    loc_org_map = dict(Location.objects.values_list("location_id", "org_id"))
    org_locations = set(
        Location.objects.filter(org_id=org_id).values_list("location_id", flat=True)
    )

    if not org_locations:
        return []

    # 2. Query System A records strictly owned by this organization
    a_qs = SystemARecord.objects.filter(location_id__in=org_locations).select_related("location")
    a_records = {
        r.record_id: {
            "record_id": r.record_id,
            "location_id": r.location_id,
            "event_date": r.event_date,
            "category_code": r.category_code,
            "actor_id": r.actor_id,
            "base_value": r.base_value,
            "adjustment": r.adjustment,
            "total_value": r.total_value,
            "state": r.state,
        }
        for r in a_qs
    }

    # 3. Query System B entries:
    # - Entries with location belonging to this org
    # - Entries referencing this org's System A records (e.g. cross-org location mismatch like REC-1077)
    b_qs = SystemBEntry.objects.filter(
        models.Q(location_id__in=org_locations) | models.Q(record_ref__in=a_records.keys())
    ).select_related("location")

    # Exclude entries that claim an org location but reference a known record owned by a DIFFERENT org
    # (these belong to the owning org's reconciliation, not this org as a false orphan)
    other_org_record_ids = set(
        SystemARecord.objects.exclude(location_id__in=org_locations).values_list("record_id", flat=True)
    )

    b_entries = []
    for b in b_qs:
        if b.record_ref in other_org_record_ids:
            # Belongs to the other org's System A transaction
            continue
        b_entries.append({
            "entry_id": b.entry_id,
            "record_ref": b.record_ref,
            "record_ref_raw": b.record_ref_raw,
            "location_id": b.location_id,
            "recorded_on": b.recorded_on,
            "value": b.value,
            "value_raw": b.value_raw,
            "label": b.label,
        })

    # Run comparison engine
    return compare_records(a_records, b_entries, loc_org_map, target_org=org_id)


@api_view(["GET"])
def disagreements_list(request):
    """
    GET /api/disagreements/?org=ORG-A&reason=VALUE_MISMATCH&sort=-value
    Returns tenant-scoped reconciliation disagreements.
    """
    org_id = request.query_params.get("org")
    if not org_id:
        return Response(
            {"error": "Query parameter 'org' is required (e.g. ?org=ORG-A)."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid_orgs = set(Location.objects.values_list("org_id", flat=True))
    if org_id not in valid_orgs:
        return Response(
            {"error": f"Invalid org '{org_id}'. Available orgs: {sorted(list(valid_orgs))}"},
            status=status.HTTP_404_NOT_FOUND,
        )

    disagreements = get_disagreements_for_org(org_id)

    # Calculate summary counts by reason for this org
    counts_by_reason: Dict[str, int] = {}
    for d in disagreements:
        r = d.get("reason", "OTHER")
        counts_by_reason[r] = counts_by_reason.get(r, 0) + 1

    # Filter by reason if requested
    reason_filter = request.query_params.get("reason")
    if reason_filter and reason_filter.upper() != "ALL":
        disagreements = [d for d in disagreements if d.get("reason") == reason_filter.upper()]

    # Filter by search term if requested
    search_query = request.query_params.get("search", "").strip().lower()
    if search_query:
        disagreements = [
            d for d in disagreements
            if search_query in str(d.get("record_id", "")).lower()
            or search_query in str(d.get("entry_id", "")).lower()
            or search_query in str(d.get("location", "")).lower()
            or search_query in str(d.get("details", "")).lower()
        ]

    # Sort results
    sort_key = request.query_params.get("sort", "").strip()
    if sort_key:
        reverse = sort_key.startswith("-")
        clean_sort = sort_key.lstrip("-").lower()

        def parse_decimal_safe(val):
            if val is None or val == "":
                return Decimal("-Infinity") if not reverse else Decimal("Infinity")
            try:
                return Decimal(str(val).replace(",", "").replace("+", ""))
            except (InvalidOperation, ValueError):
                return Decimal("-Infinity")

        if clean_sort in ("value", "b_value"):
            disagreements.sort(
                key=lambda x: parse_decimal_safe(x.get("b_value") or x.get("a_value")),
                reverse=reverse,
            )
        elif clean_sort in ("a_value", "total_value"):
            disagreements.sort(
                key=lambda x: parse_decimal_safe(x.get("a_value") or x.get("b_value")),
                reverse=reverse,
            )
        elif clean_sort == "difference":
            disagreements.sort(
                key=lambda x: parse_decimal_safe(x.get("difference")),
                reverse=reverse,
            )
        elif clean_sort in ("record_id", "record"):
            disagreements.sort(key=lambda x: str(x.get("record_id") or ""), reverse=reverse)
        elif clean_sort in ("reason", "type"):
            disagreements.sort(key=lambda x: str(x.get("reason") or ""), reverse=reverse)
        elif clean_sort in ("location", "location_id"):
            disagreements.sort(key=lambda x: str(x.get("location") or ""), reverse=reverse)
        elif clean_sort in ("date", "a_date", "b_date"):
            disagreements.sort(
                key=lambda x: str(x.get("a_date") or x.get("b_date") or ""),
                reverse=reverse,
            )

    return Response({
        "org": org_id,
        "total": len(disagreements),
        "counts_by_reason": counts_by_reason,
        "results": disagreements,
    })


@api_view(["GET"])
def orgs_list(request):
    """
    GET /api/orgs/
    Returns list of distinct organizations and their associated location IDs.
    """
    locations = Location.objects.all().order_by("org_id", "location_id")
    orgs_map: Dict[str, List[str]] = {}
    for loc in locations:
        orgs_map.setdefault(loc.org_id, []).append(loc.location_id)

    data = [
        {"org_id": org, "locations": locs, "location_count": len(locs)}
        for org, locs in sorted(orgs_map.items())
    ]
    return Response(data)
