import csv, re
from pathlib import Path
from decimal import Decimal

BASE_DIR = Path(__file__).parent / 'backend' / 'data'

def normalize_ref(raw):
    m = re.search(r'\d+', raw or '')
    return f'REC-{m.group()}' if m else None

def parse_amount(raw):
    s = (raw or '').strip().replace(',', '')
    if not s:
        return None
    try:
        return Decimal(s)
    except Exception:
        return None

with open(BASE_DIR / 'system_a.csv') as f:
    a_rows = {r['record_id']: r for r in csv.DictReader(f)}

with open(BASE_DIR / 'system_b.csv') as f:
    b_rows = list(csv.DictReader(f))

# Group B by cleaned ref
b_by_ref = {}
for b in b_rows:
    ref = normalize_ref(b['record_ref'])
    b_by_ref.setdefault(ref, []).append(b)

print('=== ORPHANS IN B ===')
for ref, entries in b_by_ref.items():
    if ref not in a_rows:
        for e in entries:
            print(f"Orphan: entry_id={e['entry_id']}, ref_raw={e['record_ref']}, norm={ref}, loc={e['location_id']}, val={e['value']}")

print('\n=== MISSING IN B ===')
for rid in a_rows:
    if rid not in b_by_ref:
        a = a_rows[rid]
        print(f"Missing in B: record_id={rid}, loc={a['location_id']}, state={a['state']}, total={a['total_value']}")

print('\n=== MULTIPLE ENTRIES IN B FOR ONE A RECORD ===')
for rid, entries in b_by_ref.items():
    if len(entries) > 1 and rid in a_rows:
        a = a_rows[rid]
        vals = [parse_amount(e['value']) for e in entries]
        print(f"Multi entry: {rid}, A total={a['total_value']}, B entries:")
        for e in entries:
            print(f"   {e['entry_id']}: val={e['value']}, label={e['label']}")
        print(f"   Sum of B vals: {sum(v for v in vals if v is not None)}, equals A: {sum(v for v in vals if v is not None) == Decimal(a['total_value'])}")

print('\n=== VALUE MISMATCHES ===')
for rid, a in a_rows.items():
    entries = b_by_ref.get(rid, [])
    if len(entries) == 1:
        e = entries[0]
        bv = parse_amount(e['value'])
        av = Decimal(a['total_value'])
        if bv is None or bv != av:
            print(f"Value mismatch: {rid}, A total={av}, B val={e['value']} (parsed={bv}), entry={e['entry_id']}")

print('\n=== VOIDED IN A ===')
for rid, a in a_rows.items():
    if a['state'] == 'VOIDED':
        entries = b_by_ref.get(rid, [])
        print(f"Voided in A: {rid}, state={a['state']}, in B entries: {[e['entry_id'] for e in entries]}")

print('\n=== LOCATION MISMATCHES ===')
for rid, a in a_rows.items():
    entries = b_by_ref.get(rid, [])
    for e in entries:
        if e['location_id'] != a['location_id']:
            print(f"Location mismatch: {rid}, A loc={a['location_id']}, B loc={e['location_id']}, entry={e['entry_id']}")

print('\n=== DATE MISMATCHES ===')
for rid, a in a_rows.items():
    entries = b_by_ref.get(rid, [])
    for e in entries:
        if e['recorded_on'] != a['event_date']:
            print(f"Date mismatch: {rid}, A date={a['event_date']}, B date={e['recorded_on']}, entry={e['entry_id']}")
