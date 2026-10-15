import urllib.request
import json
import sqlite3
import re

def _normalize(text):
    return re.sub(r'[^a-z0-9]', '', str(text).lower())

def _token_match_score(cname, dsrc, fname):
    c_tokens = set(re.findall(r'[a-z0-9]+', str(cname).lower()))
    d_tokens = set(re.findall(r'[a-z0-9]+', str(dsrc).lower()))
    target_tokens = c_tokens.union(d_tokens)
    f_tokens = set(re.findall(r'[a-z0-9]+', str(fname).lower()))
    
    if not target_tokens: return 0.0
    match_count = sum(1 for t in target_tokens if t in f_tokens)
    return match_count / len(target_tokens)

DRIVE_URL = "https://script.google.com/macros/s/AKfycbyi8U3f3c4zCns4O5GzP36h0324867_Npx0WbQ4tWbJ6fBqgEwF9vPZ2c8Qp7-3K30c/exec"
with urllib.request.urlopen(urllib.request.Request(DRIVE_URL), timeout=30) as r:
    all_drive_files = json.loads(r.read().decode())

normalized_drive = [
    (f,
     f['name'].replace('.xlsx','').replace('.xls','').replace('.csv',''),
     _normalize(f['name'].replace('.xlsx','').replace('.xls','').replace('.csv',''))
    ) for f in all_drive_files
]

camps = [
    ("Kottakkal Future", "Store Data Visited Last 3 year"),
    ("Kottayam Future", "Store Data Visited Last 3 year")
]

for camp_name, data_source in camps:
    matched_file = None; best_score = 0.0
    for (fi, raw, norm) in normalized_drive:
        # 1. Exact match on just campaign name
        if norm == _normalize(camp_name):
            matched_file = fi; best_score = 1.0; break
            
        # 2. Perfect prefix match (e.g., "Karamana_Store Data...")
        if raw.lower().startswith(str(camp_name).lower() + "_"):
            matched_file = fi; best_score = 0.95; break
            
        # 3. Exact match on campaign name + data source combined
        if norm == _normalize(str(camp_name) + str(data_source)):
            matched_file = fi; best_score = 0.90; break

        # 4. Fallback to fuzzy token matching
        score = _token_match_score(camp_name, data_source, raw)
        if score > best_score and score >= 0.50:  # Relaxed to 0.50 to tolerate minor typos
            best_score = score; matched_file = fi
            
    print(f"Camp: {camp_name} -> File: {matched_file['name'] if matched_file else 'None'} (Score: {best_score})")

