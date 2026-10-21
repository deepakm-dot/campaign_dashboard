"""
Standalone direct sync — runs _sync_campaign_data logic directly in the main process.
This bypasses threading/buffering to show real errors.
"""
import os, io, csv, json, urllib.request, base64, re, sys
from openpyxl import load_workbook
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)
import ch_db   # all campaign data lives in ClickHouse (no local database)

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)

CUSTOMER_BATCH = 200_000   # rows per ClickHouse insert
DRIVE_URL = "https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec"

NOISE = {'and','the','for','with','sale','rcs','sms','wtsp','whatsapp',
         'voice','campaign','offers','onam','data'}

def _normalize(text):
    return re.sub(r'[^a-z0-9]', '', str(text).lower())

def _word_tokens(text):
    words = re.findall(r'[a-zA-Z0-9]{3,}', str(text))
    return set(w.lower() for w in words if w.lower() not in NOISE)

def _token_match_score(camp_name, data_source, raw_file_name):
    clean_camp = camp_name.strip()
    camp_only_tokens = _word_tokens(clean_camp)
    camp_tokens = _word_tokens(clean_camp + ' ' + data_source)
    file_tokens = _word_tokens(raw_file_name)
    if not camp_only_tokens or not file_tokens: return 0.0
    
    # Check if data_source tokens are well matched
    ds_tokens = _word_tokens(data_source)
    if ds_tokens and ds_tokens.issubset(file_tokens):
        return 0.85
    
    # Store identity tokens (e.g. 'iron', 'bridge', 'falnir', 'palakkad')
    core_store_tokens = {t for t in camp_only_tokens if t not in {'future', 'mini', 'plus', 'pro', 'store', 'all', 'kerala'}}
    if core_store_tokens and not core_store_tokens.issubset(file_tokens):
        return 0.0
        
    common = camp_tokens & file_tokens
    union = camp_tokens | file_tokens
    score = len(common) / len(union) if union else 0.0
    
    # Bonus if 'future' matches on both sides
    if ('future' in camp_only_tokens) == ('future' in file_tokens):
        score += 0.15
    return score

def get_val(d, keys):
    for k in keys:
        for dk in d:
            if dk and re.sub(r'[^a-z0-9]', '', str(dk).lower()) == k:
                v = d[dk]
                if v is not None and str(v).strip() not in ('', 'None'):
                    return v
    return None

def find_header_row(sheet):
    best_row, max_vals, headers = 1, 0, []
    for i, row in enumerate(sheet.iter_rows(min_row=1, max_row=10, values_only=True), 1):
        str_vals = [c for c in row if c is not None and str(c).strip()]
        if len(str_vals) > max_vals:
            max_vals = len(str_vals); best_row = i; headers = list(row)
    return best_row, headers

def main():
    print("=== DIRECT SYNC RUN ===", flush=True)

    # Step 1: Get Drive files
    print("\n1. Fetching Drive files...", flush=True)
    all_drive_files = []
    try:
        with urllib.request.urlopen(urllib.request.Request(DRIVE_URL), timeout=120) as r:
            all_drive_files = json.loads(r.read().decode())
        print(f"   Found: {[f['name'] for f in all_drive_files]}", flush=True)
    except Exception as e:
        print(f"   DRIVE FETCH WARNING: {e}", flush=True)

    normalized_drive = [
        (f,
         f['name'].replace('.xlsx','').replace('.xls','').replace('.csv',''),
         _normalize(f['name'].replace('.xlsx','').replace('.xls','').replace('.csv',''))
        ) for f in all_drive_files
    ]

    # Collect local fallback candidates
    local_candidates = []
    for search_dir in [
        r"c:\Users\deepak.m_myg\Downloads",
        r"c:\Users\deepak.m_myg\Desktop",
        os.getcwd()
    ]:
        if os.path.exists(search_dir):
            try:
                for fname in os.listdir(search_dir):
                    if fname.startswith("~$"): continue
                    if fname.lower().endswith(('.xlsx', '.xls', '.csv')):
                        local_candidates.append(os.path.join(search_dir, fname))
            except Exception: pass

    # Step 2: Get campaigns (from ClickHouse) that don't have customers yet
    have_customers = ch_db.customer_counts()
    campaigns = [r for r in ch_db.list_campaigns() if r['id'] not in have_customers]
    print(f"\n2. Processing {len(campaigns)} campaigns needing customer files...", flush=True)

    # Step 3: Skip deletion to preserve old data
    print("   Preserving existing campaign_customers data.", flush=True)

    # Step 4: Match + download + insert
    processed = 0

    for camp in campaigns:
        camp_id = camp['id']
        camp_name = camp['campaign_name'].strip()
        data_source = (camp['data_source'] or '').strip()
        camp_group = (camp['campaign_group'] or '').strip()
        start_date = camp['start_date']

        # Determine expected month string (e.g. "SEPTEMBER 2026")
        expected_month = ""
        month_name = ""
        if start_date:
            try:
                d = datetime.strptime(start_date[:10], '%Y-%m-%d')
                expected_month = f"{d.strftime('%B').upper()} {d.year}"
                month_name = d.strftime('%B').lower()
            except Exception: pass

        # Match Drive files
        matched_file = None; best_score = 0.0
        clean_cn = _normalize(camp_name)
        clean_cg = _normalize(camp_group)
        clean_ds = _normalize(data_source)

        for (fi, raw, norm) in normalized_drive:
            parent_path = str(fi.get('parentPath') or '').lower()
            folder_name = str(fi.get('folder') or '').lower()
            full_loc = parent_path + ' ' + folder_name + ' ' + raw.lower()
            
            # Exact match on normalized campaign name
            if norm == clean_cn:
                matched_file = fi; best_score = 1.0; break
                
            # Perfect prefix match (e.g., "Karamana_Store Data...")
            if raw.lower().startswith(camp_name.lower() + "_") or raw.lower().startswith(clean_cn + "_"):
                matched_file = fi; best_score = 0.95; break
                
            # Exact match on campaign name + data source combined
            if norm == _normalize(camp_name + data_source):
                matched_file = fi; best_score = 0.92; break

            # Exact match on data_source
            if clean_ds and (norm == clean_ds or clean_ds in norm):
                matched_file = fi; best_score = 0.90; break

            # Fuzzy token matching
            score = _token_match_score(camp_name, data_source, raw)
            
            # Add month preference bonus
            if month_name and month_name in full_loc:
                score += 0.10
            if clean_cg and (clean_cg in _normalize(full_loc) or clean_cn in _normalize(full_loc)):
                score += 0.15

            if score > best_score and score >= 0.50:
                best_score = score
                matched_file = fi

        # Local directory fallback if no Drive match
        local_matched_path = None
        if not matched_file:
            local_best_score = 0.0
            for fpath in local_candidates:
                fname = os.path.basename(fpath).lower()
                norm_local = _normalize(os.path.splitext(fname)[0])
                if norm_local == clean_cn:
                    local_matched_path = fpath; break
                if norm_local == _normalize(camp_name + data_source) or (clean_ds and clean_ds in norm_local):
                    local_matched_path = fpath; break
                if clean_cg and clean_cg in norm_local:
                    local_matched_path = fpath; break
                score = _token_match_score(camp_name, data_source, fname)
                if score > local_best_score and score >= 0.50:
                    local_best_score = score
                    local_matched_path = fpath

        if not matched_file and not local_matched_path:
            print(f"   [{camp_id}] No matching Drive or Local file for '{camp_name}' (best_score={best_score:.2f})", flush=True)
            continue

        content = None
        file_name = ''
        if matched_file:
            file_id = matched_file.get('id')
            file_name = matched_file.get('name', '').lower()
            print(f"\n   [{camp_id}] '{camp_name}' ({camp['type']}) → Drive '{matched_file['name']}' score={best_score:.2f}", flush=True)
            print(f"   Downloading {file_id}...", flush=True)
            try:
                import http.cookiejar
                cj = http.cookiejar.CookieJar()
                opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
                dl_url = f"https://drive.google.com/uc?id={file_id}&export=download"
                dl_req = urllib.request.Request(dl_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                with opener.open(dl_req, timeout=120) as r:
                    content = r.read()
                if content[:2] != b'PK':
                    html_text = content.decode('utf-8', errors='ignore')
                    uuid_m = re.search(r'name="uuid"\s+value="([^"]+)"', html_text)
                    uuid_val = uuid_m.group(1) if uuid_m else ''
                    dl_url2 = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t&uuid={uuid_val}"
                    dl_req2 = urllib.request.Request(dl_url2, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
                    with opener.open(dl_req2, timeout=240) as r2:
                        content = r2.read()
                print(f"   Downloaded: {len(content):,} bytes, Is XLSX: {content[:2] == b'PK'}", flush=True)
            except Exception as e:
                print(f"   DOWNLOAD ERROR: {e}", flush=True); continue
        else:
            file_name = os.path.basename(local_matched_path).lower()
            print(f"\n   [{camp_id}] '{camp_name}' ({camp['type']}) → Local '{local_matched_path}'", flush=True)

        # Parse customers with streaming/read_only=True and bulk-insert into ClickHouse
        print(f"   Parsing...", flush=True)
        inserted = 0
        batch = []

        def flush_batch():
            nonlocal inserted, batch
            if batch:
                ch_db.insert_customers(camp_id, batch)
                inserted += len(batch)
                batch = []

        try:
            is_xlsx = file_name.endswith('.xlsx') or file_name.endswith('.xls') or (content and content[:2] == b'PK')
            if is_xlsx:
                source = local_matched_path if local_matched_path else io.BytesIO(content)
                wb = load_workbook(source, read_only=True)
                for sheet_name in wb.sheetnames:
                    sheet = wb[sheet_name]
                    print(f"   Reading sheet '{sheet_name}'...", flush=True)
                    for row in sheet.iter_rows(values_only=True):
                        if not row or not any(row): continue
                        raw_cell = str(row[0] or '')
                        clean = re.sub(r'\D', '', raw_cell)
                        if len(clean) >= 10:
                            batch.append(clean[-10:])
                            if len(batch) >= CUSTOMER_BATCH:
                                flush_batch()
                    flush_batch()
            elif file_name.endswith('.csv'):
                if local_matched_path:
                    with open(local_matched_path, 'r', encoding='utf-8', errors='ignore') as f:
                        reader = csv.reader(f)
                        for row in reader:
                            if not any(row): continue
                            clean = re.sub(r'\D', '', str(row[0] or ''))
                            if len(clean) >= 10:
                                batch.append(clean[-10:])
                                if len(batch) >= CUSTOMER_BATCH:
                                    flush_batch()
                else:
                    reader = csv.reader(io.StringIO(content.decode('utf-8', errors='ignore')))
                    for row in reader:
                        if not any(row): continue
                        clean = re.sub(r'\D', '', str(row[0] or ''))
                        if len(clean) >= 10:
                            batch.append(clean[-10:])
                            if len(batch) >= CUSTOMER_BATCH:
                                flush_batch()
                flush_batch()
        except Exception as e:
            import traceback
            print(f"   PARSE ERROR: {e}", flush=True)
            traceback.print_exc()
            # Don't leave a half-loaded audience behind: it would hide this campaign from the next run
            try:
                ch_db.delete_customers(camp_id)
            except Exception as e_del:
                print(f"   CLEANUP ERROR: {e_del}", flush=True)
            continue

        print(f"   Inserted {inserted:,} customers for [{camp_id}] '{camp_name}' into ClickHouse.", flush=True)
        processed += 1

    print(f"\n=== DONE: {processed} campaigns processed ===", flush=True)

if __name__ == '__main__':
    main()
