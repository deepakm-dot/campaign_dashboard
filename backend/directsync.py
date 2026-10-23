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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
KPI_RESET = {'purchase_count': 0, 'purchase_value': 0.0, 'conversion_rate': 0.0, 'roi': 0.0,
             'new_customers': 0, 'existing_customers': 0}
FP_PREFIX = 'drive_fp:'          # config key per campaign: fingerprint of the customer file last loaded
TRUST_PREFIX = 'drive_fp_trusted:'   # set once THIS sync loaded the campaign's customers from that file
MIN_SIMILARITY = 0.5             # unverified replacement file must be >= 50% similar (Jaccard) to the current customers
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def match_campaign(camp, normalized_drive, local_candidates):
    """Find the customer file (Drive first, then local folders) for a campaign.
    Returns (drive_file_info | None, local_path | None, best_score)."""
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
    return matched_file, local_matched_path, best_score


def file_key(matched_file, local_path):
    return f"drive:{matched_file.get('id')}" if matched_file else f"local:{local_path}"


def fingerprint(matched_file, local_path):
    """Cheap change detector for a customer file: id | size | last-modified | name.
    Drive: one HEAD request (no download). Local: file size and mtime. None if unavailable."""
    try:
        if matched_file:
            fid = matched_file.get('id')
            url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
            req = urllib.request.Request(url, method='HEAD', headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                size = r.headers.get('Content-Length') or ''
                modified = r.headers.get('Last-Modified') or ''
            if not size and not modified:
                return None
            return f"{fid}|{size}|{modified}|{matched_file.get('name', '')}"
        st = os.stat(local_path)
        return f"local|{st.st_size}|{int(st.st_mtime)}|{os.path.basename(local_path)}"
    except Exception as e:
        print(f"   (fingerprint unavailable: {e})", flush=True)
        return None


def fingerprints(targets):
    """{file_key: fingerprint} for {file_key: (matched_file, local_path)}, checked in parallel."""
    from concurrent.futures import ThreadPoolExecutor
    keys = list(targets)
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda k: fingerprint(*targets[k]), keys))
    return dict(zip(keys, results))


def download_drive_file(file_id):
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    dl_url = f"https://drive.google.com/uc?id={file_id}&export=download"
    dl_req = urllib.request.Request(dl_url, headers=UA)
    with opener.open(dl_req, timeout=120) as r:
        content = r.read()
    if content[:2] != b'PK':
        html_text = content.decode('utf-8', errors='ignore')
        uuid_m = re.search(r'name="uuid"\s+value="([^"]+)"', html_text)
        uuid_val = uuid_m.group(1) if uuid_m else ''
        dl_url2 = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t&uuid={uuid_val}"
        dl_req2 = urllib.request.Request(dl_url2, headers=UA)
        with opener.open(dl_req2, timeout=240) as r2:
            content = r2.read()
    print(f"   Downloaded: {len(content):,} bytes, Is XLSX: {content[:2] == b'PK'}", flush=True)
    return content


def iter_mobiles(content, file_name, local_path):
    """Stream the 10-digit mobile numbers out of an xlsx / csv customer file (first column)."""
    is_xlsx = file_name.endswith('.xlsx') or file_name.endswith('.xls') or (content and content[:2] == b'PK')
    if is_xlsx:
        source = local_path if local_path else io.BytesIO(content)
        wb = load_workbook(source, read_only=True)
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            print(f"   Reading sheet '{sheet_name}'...", flush=True)
            for row in sheet.iter_rows(values_only=True):
                if not row or not any(row): continue
                clean = re.sub(r'\D', '', str(row[0] or ''))
                if len(clean) >= 10:
                    yield clean[-10:]
    elif file_name.endswith('.csv'):
        if local_path:
            with open(local_path, 'r', encoding='utf-8', errors='ignore') as f:
                for row in csv.reader(f):
                    if not any(row): continue
                    clean = re.sub(r'\D', '', str(row[0] or ''))
                    if len(clean) >= 10:
                        yield clean[-10:]
        else:
            for row in csv.reader(io.StringIO(content.decode('utf-8', errors='ignore'))):
                if not any(row): continue
                clean = re.sub(r'\D', '', str(row[0] or ''))
                if len(clean) >= 10:
                    yield clean[-10:]


def load_customers(camp, matched_file, local_path, target_id, score=0.0):
    """Download/parse the customer file and bulk-insert its mobiles into ClickHouse under `target_id`.
    Returns the number inserted, or None if the file could not be downloaded."""
    camp_id = camp['id']
    camp_name = camp['campaign_name'].strip()
    content = None
    if matched_file:
        file_id = matched_file.get('id')
        file_name = matched_file.get('name', '').lower()
        print(f"\n   [{camp_id}] '{camp_name}' ({camp['type']}) → Drive '{matched_file['name']}' score={score:.2f}", flush=True)
        print(f"   Downloading {file_id}...", flush=True)
        try:
            content = download_drive_file(file_id)
        except Exception as e:
            print(f"   DOWNLOAD ERROR: {e}", flush=True)
            return None
    else:
        file_name = os.path.basename(local_path).lower()
        print(f"\n   [{camp_id}] '{camp_name}' ({camp['type']}) → Local '{local_path}'", flush=True)

    print(f"   Parsing...", flush=True)
    inserted = 0
    batch = []
    for mobile in iter_mobiles(content, file_name, local_path):
        batch.append(mobile)
        if len(batch) >= CUSTOMER_BATCH:
            ch_db.insert_customers(target_id, batch)
            inserted += len(batch)
            batch = []
    if batch:
        ch_db.insert_customers(target_id, batch)
        inserted += len(batch)
    # Sanity check: what is stored must equal what was sent (guards against duplicated or lost inserts)
    stored = ch_db.count_customers(target_id)
    if stored != inserted:
        raise RuntimeError(f"row count mismatch after load: sent {inserted:,}, stored {stored:,}")
    return inserted


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

    # Step 2: Campaigns (from ClickHouse), which already have customers, and which file each one maps to
    left = ch_db.delete_staging()
    if left:
        print(f"   Cleaned {left:,} leftover staging rows from an interrupted reload.", flush=True)
    campaigns = ch_db.list_campaigns(order_by='id')
    have_customers = ch_db.customer_counts()
    stored_fp = ch_db.get_configs(FP_PREFIX)
    trusted = ch_db.get_configs(TRUST_PREFIX)
    matches = {c['id']: match_campaign(c, normalized_drive, local_candidates) for c in campaigns}

    # Step 3: Detect NEW and CHANGED customer files
    to_check = {}
    for camp in campaigns:
        mf, lp, _ = matches[camp['id']]
        if camp['id'] in have_customers and (mf or lp):
            to_check[file_key(mf, lp)] = (mf, lp)
    print(f"\n2. Checking {len(to_check)} customer files for changes (size / last-modified)...", flush=True)
    current_fp = fingerprints(to_check) if to_check else {}

    work = []                # (campaign, reason)
    new_baselines = {}       # fingerprints to remember without reloading
    for camp in campaigns:
        cid = camp['id']
        mf, lp, _ = matches[cid]
        if cid not in have_customers:
            work.append((camp, 'new', False))
            continue
        if not (mf or lp):
            continue
        fp = current_fp.get(file_key(mf, lp))
        if not fp:
            continue
        old = stored_fp.get(f"{FP_PREFIX}{cid}")
        if not old:
            new_baselines[f"{FP_PREFIX}{cid}"] = fp      # first time seen: remember it, keep loaded customers
        elif old != fp:
            o, n = old.split('|', 3), fp.split('|', 3)
            same_id, same_name = o[0] == n[0], (o[3] if len(o) > 3 else '') == (n[3] if len(n) > 3 else '')
            if same_id or same_name:
                # same file edited in place, or re-uploaded under the same name -> reload it.
                # If this sync never loaded the campaign from that file (legacy data), verify first.
                work.append((camp, 'updated', f"{TRUST_PREFIX}{cid}" not in trusted))
            else:
                # the matcher now points at a different file; just remember it (never reload from a guess)
                new_baselines[f"{FP_PREFIX}{cid}"] = fp
    if new_baselines:
        ch_db.set_configs(new_baselines)
        print(f"   Remembered {len(new_baselines)} file fingerprints.", flush=True)
    n_new = sum(1 for _, r, _v in work if r == 'new')
    print(f"\n3. Processing {n_new} new campaigns and {len(work) - n_new} updated customer files...", flush=True)

    # Step 4: Match + download + insert
    processed = 0
    staged = {}                  # file_key -> (staging campaign_id, rows) ; each file is downloaded once per run
    stage_ids = iter(range(-1_000_000_000, -2_000_000_000, -1))

    def stage_file(key, camp, mf, lp, score):
        if key not in staged:
            sid = next(stage_ids)
            try:
                n = load_customers(camp, mf, lp, sid, score)
            except Exception:
                try: ch_db.delete_customers(sid)
                except Exception: pass
                raise
            staged[key] = (sid, n) if n is not None else None
        return staged[key]

    for camp, reason, verify in work:
        camp_id = camp['id']
        camp_name = camp['campaign_name'].strip()
        mf, lp, score = matches[camp_id]

        if not mf and not lp:
            print(f"   [{camp_id}] No matching Drive or Local file for '{camp_name}' (best_score={score:.2f})", flush=True)
            continue

        began_swap = False
        try:
            if reason == 'new':
                inserted = load_customers(camp, mf, lp, camp_id, score)
                if inserted is None:
                    continue
            else:
                # Updated files are loaded into a staging id first and replace the old customers only once
                # the whole file was read, so a failure never loses the old audience.
                st = stage_file(file_key(mf, lp), camp, mf, lp, score)
                if not st:
                    continue
                stage_id, inserted = st
                if verify:
                    # Legacy campaign: we never loaded it from this file ourselves, so make sure the file
                    # really is its audience before replacing it: current and new customers must be similar.
                    cur = f"source_db = '{ch_db.SRC}' AND campaign_id = {camp_id}"
                    stg = f"source_db = '{ch_db.SRC}' AND campaign_id = {stage_id}"
                    total = int(ch_db.query(f"SELECT uniqExact(customer_mobile) AS n FROM {ch_db.T_CUST} WHERE {cur}")[0]['n'])
                    new_n = int(ch_db.query(f"SELECT uniqExact(customer_mobile) AS n FROM {ch_db.T_CUST} WHERE {stg}")[0]['n'])
                    hit = int(ch_db.query(f"SELECT uniqExact(customer_mobile) AS n FROM {ch_db.T_CUST} WHERE {cur} "
                                          f"AND customer_mobile IN (SELECT customer_mobile FROM {ch_db.T_CUST} WHERE {stg})")[0]['n'])
                    union = total + new_n - hit
                    if total > 0 and union > 0 and hit / union < MIN_SIMILARITY:
                        fp_rej = fingerprint(mf, lp)
                        if fp_rej:
                            ch_db.set_configs({f"{FP_PREFIX}{camp_id}": fp_rej})
                        print(f"   SKIPPED [{camp_id}] '{camp_name}': '{(mf or {}).get('name', lp)}' ({new_n:,} numbers) is not "
                              f"this campaign's audience ({total:,} current customers, {hit:,} in common) - keeping existing customers.", flush=True)
                        continue
                began_swap = True
                ch_db.delete_customers(camp_id)
                ch_db.copy_customers(stage_id, camp_id)
                ch_db.update_campaign(camp_id, KPI_RESET)   # fixkpi recalculates the sales attribution next
        except Exception as e:
            import traceback
            print(f"   LOAD ERROR: {e}", flush=True)
            traceback.print_exc()
            # Don't leave a half-loaded audience behind (an untouched old audience is kept as is)
            if reason == 'new' or began_swap:
                try:
                    ch_db.delete_customers(camp_id)
                except Exception as e_del:
                    print(f"   CLEANUP ERROR: {e_del}", flush=True)
            continue

        fp = fingerprint(mf, lp)
        if fp:
            # this sync loaded the customers from this file, so later edits to it can be trusted
            ch_db.set_configs({f"{FP_PREFIX}{camp_id}": fp, f"{TRUST_PREFIX}{camp_id}": '1'})
        action = 'Reloaded' if reason == 'updated' else 'Inserted'
        print(f"   {action} {inserted:,} customers for [{camp_id}] '{camp_name}' into ClickHouse.", flush=True)
        processed += 1

    if staged:
        ch_db.delete_staging()
    print(f"\n=== DONE: {processed} campaigns processed ===", flush=True)

if __name__ == '__main__':
    main()
