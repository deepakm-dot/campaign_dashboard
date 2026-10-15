"""
Standalone sync script - runs _sync_campaign_data logic directly with full debug output.
Does NOT import main.py (to avoid starting the Bottle server).
"""
import sqlite3, json, io, re, urllib.request, base64, csv
from openpyxl import load_workbook

DB_PATH = 'campaign_dashboard.db'
DRIVE_URL = "https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Step 1: Test Drive URL
print("=== Step 1: Fetching Drive file list ===")
try:
    req = urllib.request.Request(DRIVE_URL)
    with urllib.request.urlopen(req, timeout=30) as res:
        all_drive_files = json.loads(res.read().decode())
    print(f"Found {len(all_drive_files)} files:")
    for f in all_drive_files:
        print(f"  - {f.get('name')} (id={f.get('id')})")
except Exception as e:
    print(f"ERROR fetching Drive files: {e}")
    exit(1)

print()

# Step 2: Check campaigns in DB
print("=== Step 2: Current campaigns in DB ===")
conn = get_db()
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM campaigns")
print(f"Total campaigns: {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM campaign_customers")
print(f"Total campaign_customers: {c.fetchone()[0]}")

# Check Vypin/Paravoor specifically
c.execute("SELECT id, campaign_name, type, data_source FROM campaigns WHERE campaign_name LIKE '%Vypin%' OR campaign_name LIKE '%Paravoor%'")
print("Vypin/Paravoor campaigns:")
for r in c.fetchall():
    print(f"  [{r['id']}] {r['campaign_name']} | {r['type']} | data_source='{r['data_source']}'")
conn.close()

print()

# Step 3: Simulate matching
print("=== Step 3: Matching simulation ===")
NOISE = {'and','the','for','with','sale','rcs','sms','wtsp','whatsapp',
         'voice','campaign','offers','onam','data'}

def _word_tokens(text):
    words = re.findall(r'[a-zA-Z]{3,}', str(text))
    return set(w.lower() for w in words if w.lower() not in NOISE)

def _token_match_score(camp_name, data_source, raw_file_name):
    camp_tokens = _word_tokens(camp_name + ' ' + data_source)
    file_tokens = _word_tokens(raw_file_name)
    if not camp_tokens or not file_tokens: return 0.0
    return len(camp_tokens & file_tokens) / len(camp_tokens)

def _normalize(text):
    return re.sub(r'[^a-z0-9]', '', str(text).lower())

normalized_drive = [
    (f, f['name'].replace('.xlsx','').replace('.xls','').replace('.csv',''),
     _normalize(f['name'].replace('.xlsx','').replace('.xls','').replace('.csv','')))
    for f in all_drive_files
]

conn = get_db()
c = conn.cursor()
c.execute("SELECT id, campaign_name, type, data_source FROM campaigns WHERE campaign_name LIKE '%Vypin%' OR campaign_name LIKE '%Paravoor%'")
camps = c.fetchall()
conn.close()

for camp in camps:
    data_source = camp['data_source'] or ''
    if 'external' in data_source.lower():
        print(f"  [{camp['id']}] {camp['campaign_name']} | {camp['type']} | SKIPPED (external data)")
        continue
    best_score = 0.0
    matched = None
    for (fi, raw, norm) in normalized_drive:
        if norm == _normalize(camp['campaign_name']):
            matched = fi['name']; best_score = 1.0; break
        score = _token_match_score(camp['campaign_name'], data_source, raw)
        if score > best_score and score >= 0.60:
            best_score = score; matched = fi['name']
    print(f"  [{camp['id']}] {camp['campaign_name']} | {camp['type']} | data='{data_source}' | {'MATCHED: '+matched+f' (score={best_score:.2f})' if matched else 'NO MATCH'}")
