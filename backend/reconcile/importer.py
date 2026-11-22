import csv
import logging
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.db import transaction
from .models import Location, SystemARecord, SystemBEntry

logger = logging.getLogger(__name__)


def normalize_ref(raw: str) -> str | None:
    """
    Normalizes dirty record reference strings to standard 'REC-XXXX' format.
    Handles lowercase, spacing, missing prefixes:
      'rec1034'       -> 'REC-1034'
      ' REC - 1070 '  -> 'REC-1070'
      '1112'          -> 'REC-1112'
      'REC-1001'      -> 'REC-1001'
    Returns None if no numeric digits are found.
    """
    if not raw:
        return None
    m = re.search(r"\d+", raw.strip())
    return f"REC-{m.group()}" if m else None


def parse_amount(raw: str) -> Decimal | None:
    """
    Parses currency values into Decimal objects.
    Handles Indian-style commas e.g. '1,25,400.00' -> Decimal('125400.00').
    CRITICAL: Empty, blank, or invalid values return None (NULL in DB), NEVER Decimal('0.00').
    Zero is a valid balance/transaction amount; missing data is unknown.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        logger.warning(f"Failed to parse amount from raw string: {raw!r}")
        return None


def parse_date(raw: str):
    """
    Parses ISO date string 'YYYY-MM-DD' into date object.
    Returns None if missing or invalid without crashing.
    """
    if not raw:
        return None
    s = raw.strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse date string: {raw!r}")
        return None


def import_all_data(data_dir: Path | str | None = None) -> dict:
    """
    Orchestrates idempotent loading of locations.csv, system_a.csv, and system_b.csv.
    Guarantees every row in every CSV produces exactly one DB row.
    Returns detailed audit stats.
    """
    if data_dir is None:
        data_dir = Path(__file__).resolve().parent.parent / "data"
    else:
        data_dir = Path(data_dir)

    stats = {}
    with transaction.atomic():
        stats["locations"] = import_locations(data_dir / "locations.csv")
        stats["system_a"] = import_system_a(data_dir / "system_a.csv")
        stats["system_b"] = import_system_b(data_dir / "system_b.csv")

    return stats


def import_locations(filepath: Path | str) -> dict:
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Locations file not found: {filepath}")

    read_count = 0
    saved_count = 0

    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            read_count += 1
            cleaned_row = {k.strip(): (v.strip() if v else "") for k, v in row.items()}
            loc_id = cleaned_row.get("location_id")
            org_id = cleaned_row.get("org_id")
            name = cleaned_row.get("location_name") or loc_id

            Location.objects.update_or_create(
                location_id=loc_id,
                defaults={
                    "org_id": org_id,
                    "location_name": name,
                },
            )
            saved_count += 1

    return {"read": read_count, "saved": saved_count}


def import_system_a(filepath: Path | str) -> dict:
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"System A file not found: {filepath}")

    read_count = 0
    saved_count = 0
    blank_actors = 0
    locations_cache = {loc.location_id: loc for loc in Location.objects.all()}

    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            read_count += 1
            cleaned = {k.strip(): (v.strip() if v is not None else "") for k, v in row.items()}
            
            rec_id = cleaned.get("record_id")
            loc_id = cleaned.get("location_id")
            loc_obj = locations_cache.get(loc_id)
            event_date = parse_date(cleaned.get("event_date"))
            category = cleaned.get("category_code", "")
            actor = cleaned.get("actor_id") or None
            if not actor:
                blank_actors += 1

            base_val = parse_amount(cleaned.get("base_value")) or Decimal("0.00")
            adj_val = parse_amount(cleaned.get("adjustment")) or Decimal("0.00")
            tot_val = parse_amount(cleaned.get("total_value")) or (base_val + adj_val)
            state = cleaned.get("state", "CONFIRMED").upper()

            SystemARecord.objects.update_or_create(
                record_id=rec_id,
                defaults={
                    "location": loc_obj,
                    "event_date": event_date,
                    "category_code": category,
                    "actor_id": actor,
                    "base_value": base_val,
                    "adjustment": adj_val,
                    "total_value": tot_val,
                    "state": state,
                },
            )
            saved_count += 1

    return {"read": read_count, "saved": saved_count, "blank_actors": blank_actors}


def import_system_b(filepath: Path | str) -> dict:
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"System B file not found: {filepath}")

    read_count = 0
    saved_count = 0
    values_left_empty = 0
    refs_cleaned = 0
    locations_cache = {loc.location_id: loc for loc in Location.objects.all()}

    with open(filepath, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            read_count += 1
            cleaned = {k.strip(): (v.strip() if v is not None else "") for k, v in row.items() if k}

            entry_id = cleaned.get("entry_id")
            ref_raw = cleaned.get("record_ref", "")
            norm_ref = normalize_ref(ref_raw)
            if norm_ref and norm_ref != ref_raw:
                refs_cleaned += 1

            loc_id = cleaned.get("location_id")
            loc_obj = locations_cache.get(loc_id)
            recorded_on = parse_date(cleaned.get("recorded_on"))
            val_raw = cleaned.get("value", "")
            parsed_val = parse_amount(val_raw)
            if parsed_val is None:
                values_left_empty += 1

            label = cleaned.get("label", "")

            SystemBEntry.objects.update_or_create(
                entry_id=entry_id,
                defaults={
                    "record_ref_raw": ref_raw,
                    "record_ref": norm_ref,
                    "location": loc_obj,
                    "recorded_on": recorded_on,
                    "value_raw": val_raw,
                    "value": parsed_val,
                    "label": label,
                },
            )
            saved_count += 1

    return {
        "read": read_count,
        "saved": saved_count,
        "values_left_empty": values_left_empty,
        "refs_cleaned": refs_cleaned,
    }
