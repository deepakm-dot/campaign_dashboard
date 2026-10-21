"""
Fix target_size for current campaigns using SMS Delivered from Google Sheets,
then re-run KPI calculation so the dashboard shows correct Audience Reached.

All campaign data is read from / written to the ClickHouse campaign_dashboard_* tables
(see ch_db.py). There is no local database.
"""
import json, urllib.request, base64, re, sys
sys.stdout.reconfigure(line_buffering=True)

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)
import ch_db

SHEETS_URL = "https://script.google.com/macros/s/AKfycbwLu3feQq0BCxUFFxpUhamKLfNa5njxmJLZ4yBRY9pmPtsgBIXEFSzeVADBt5hlG9Y_DQ/exec"
CH_URL  = ch_db.CH_URL
CH_USER = ch_db.CH_USER
CH_PASS = ch_db.CH_PASS
SRC = ch_db.SRC
T_CAMP, T_CUST = ch_db.T_CAMP, ch_db.T_CUST


def load_branch_map():
    import openpyxl, re
    branch_map = {}
    try:
        wb = openpyxl.load_workbook('Book1.xlsx', data_only=True)
        for row in wb.active.iter_rows(min_row=2, values_only=True):
            if row[0] and row[1]:
                # Keep full name without spaces for exact matching
                full_clean = re.sub(r'[^a-z0-9]', '', str(row[1]).lower())
                branch_map[full_clean] = str(row[0]).strip()
                
                # Also keep the fallback logic but only if not already mapped
                clean_name = re.sub(r'(?i)\s*(FUTURE|DIGITAL|STORE)$', '', str(row[1])).strip().lower()
                first_word = clean_name.split()[0]
                if first_word not in branch_map:
                    branch_map[first_word] = str(row[0]).strip()
    except: pass
    return branch_map

BRANCH_MAP = load_branch_map()

def query_clickhouse(sql):
    try:
        return ch_db.query(sql, timeout=120)
    except Exception as e:
        print(f"  ClickHouse ERROR: {e}", flush=True); return []

_CH_BRANCHES = None
def get_ch_branches():
    global _CH_BRANCHES
    if _CH_BRANCHES is None:
        _CH_BRANCHES = query_clickhouse("SELECT code, branch_name FROM branch_master")
    return _CH_BRANCHES or []

def resolve_branch_dynamic(camp_name):
    if not camp_name or 'all kerala' in camp_name.lower():
        return ''
    clean = re.sub(r'[^a-z0-9]', '', camp_name.lower())
    b = BRANCH_MAP.get(clean)
    if b: return b
    first_word = re.sub(r'[^a-z]', '', camp_name.lower().split()[0])
    b = BRANCH_MAP.get(first_word)
    if b: return b
    
    # Dynamic ClickHouse branch_master resolution for newly opened stores
    branches = get_ch_branches()
    has_future = 'future' in camp_name.lower()
    words = [w for w in re.findall(r'[a-zA-Z]{3,}', camp_name.lower()) 
             if w not in {'future','store','digital','sale','offer','offers','campaign','special','support','data','august','september','october','inauguration'}]
    for w in words:
        for br in branches:
            bname = br.get('branch_name','').lower()
            if w in bname and ('future' in bname) == has_future:
                return br.get('code','')
    return ''

def _differs(old, new):
    """True when a stored value differs from the new one (floats compared with a tolerance)."""
    if isinstance(new, float) or isinstance(old, float):
        try:
            return abs(float(old or 0) - float(new or 0)) > 1e-6
        except Exception:
            return True
    return (old or '') != (new or '') if isinstance(new, str) else (old or 0) != (new or 0)

def _update_if_changed(camp, fields):
    """Run one ClickHouse UPDATE only for the fields that actually changed."""
    changed = {k: v for k, v in fields.items() if _differs(camp.get(k), v)}
    if changed:
        ch_db.update_campaign(camp['id'], changed)
        camp.update(changed)
    return bool(changed)

# Step 0: Re-link orphaned campaign_customers to current campaign IDs
print("=== Step 0: Re-linking orphaned campaign_customers ===", flush=True)

# Find all campaign_ids in campaign_customers that no longer exist in campaigns
orphan_ids = [int(r['campaign_id']) for r in ch_db.query(
    f"SELECT DISTINCT campaign_id FROM {T_CUST} "
    f"WHERE source_db = '{SRC}' AND campaign_id NOT IN (SELECT id FROM {T_CAMP} WHERE source_db = '{SRC}')")]
print(f"  Orphaned campaign_ids: {orphan_ids}", flush=True)

for orphan_id in orphan_ids:
    # Get a sample customer row to find the store_name (used to identify campaign)
    sample = ch_db.query(f"SELECT store_name FROM {T_CUST} WHERE source_db = '{SRC}' AND campaign_id = {orphan_id} LIMIT 1")
    store = (sample[0]['store_name'] or '').strip() if sample else ''
    print(f"  Orphan {orphan_id}: store_name='{store}'", flush=True)

    # Find matching current campaign by store name keyword in campaign_name
    if store:
        keyword = store.split()[0].lower() if store else ''
        matches = [m for m in ch_db.list_campaigns() if keyword in (m.get('campaign_name') or '').lower()]
        if matches:
            # Pick first match
            new_id = matches[0]['id']
            ch_db.execute(f"ALTER TABLE {T_CUST} UPDATE campaign_id = {int(new_id)} "
                          f"WHERE source_db = '{SRC}' AND campaign_id = {orphan_id}")
            print(f"  -> Re-linked {orphan_id} -> {new_id} ({matches[0]['campaign_name']})", flush=True)
        else:
            print(f"  -> No match found for store '{store}'", flush=True)
    else:
        print(f"  -> No store_name to match on", flush=True)

# Step 1: Fetch SMS Delivered values from sheet
print("\n=== Step 1: Fetching SMS Delivered from Google Sheets ===", flush=True)
with urllib.request.urlopen(urllib.request.Request(SHEETS_URL), timeout=30) as r:
    sheet_rows = json.loads(r.read().decode())


# Build lookup: (sl_no, sheet_tab) and (name, mode, group) -> sms_delivered
sms_lookup = {}
for row in sheet_rows:
    sl = int(row.get('Sl', 0) or 0)
    tab = str(row.get('_sheet_tab', '')).strip()
    name = str(row.get('Campaign Name', '')).strip().lower()
    mode = str(row.get('Campaign Mode', '')).strip().lower()
    group = str(row.get('Campaign Group', '')).strip().lower()
    ds   = str(row.get('Data ', '') or row.get('Data', '')).strip().lower()
    delivered = int(row.get('SMS Delivered', 0) or 0)
    if sl > 0 and tab:
        sms_lookup[(sl, tab)] = delivered
    if name and mode and group:
        sms_lookup[(name, mode, group)] = delivered
    sms_lookup[(name, mode, ds)] = delivered
    if delivered > 0:
        print(f"  [{sl}] {row.get('Campaign Name')} | {row.get('Campaign Mode')} | {row.get('Campaign Group')} → SMS Delivered={delivered}", flush=True)

# Step 2: Update target_size in campaigns table
print("\n=== Step 2: Updating target_size in campaigns table ===", flush=True)
all_camps = ch_db.list_campaigns()
for camp in all_camps:
    delivered = 0
    if camp['sl_no'] and camp['sheet_tab']:
        delivered = sms_lookup.get((camp['sl_no'], camp['sheet_tab']), 0)
    if not delivered and camp['campaign_group']:
        delivered = sms_lookup.get((camp['campaign_name'].strip().lower(), camp['type'].strip().lower(), camp['campaign_group'].strip().lower()), 0)
    if not delivered:
        delivered = sms_lookup.get((camp['campaign_name'].strip().lower(), camp['type'].strip().lower(), (camp['data_source'] or '').strip().lower()), 0)
    if delivered > 0:
        if _update_if_changed(camp, {'target_size': int(delivered)}):
            print(f"  [{camp['id']}] {camp['campaign_name']} | {camp['type']} → target_size={delivered}", flush=True)

# Step 3: Re-run KPI calc for campaigns with customers
print("\n=== Step 3: Re-calculating KPIs ===", flush=True)
cust_counts = ch_db.customer_counts()
camps = [cp for cp in all_camps if cust_counts.get(cp['id'], 0) > 0]
print(f"Found {len(camps)} campaigns with customers.", flush=True)

for camp in camps:
    camp_id      = camp['id']
    camp_name    = camp['campaign_name']
    start_dt     = camp['start_date']
    end_dt       = camp['end_date'] or start_dt
    budget       = camp['budget'] or 0
    branch       = camp['branch_code'] or ''
    sms_delivered = camp['target_size'] or 0
    
    p_cnt = int(camp['purchase_count'] or 0)
    n_cnt = int(camp['new_customers'] or 0)
    e_cnt = int(camp['existing_customers'] or 0)
    
    if p_cnt > 0 and (n_cnt + e_cnt) == p_cnt:
        # Reconcile conversion rate & ROI with latest sheet values (budget & sms_delivered)
        conv_rate = (p_cnt / sms_delivered * 100) if sms_delivered > 0 else 0
        p_val = float(camp['purchase_value'] or 0)
        roi = (p_val / budget) if budget > 0 else 0
        _update_if_changed(camp, {'conversion_rate': float(conv_rate), 'roi': float(roi),
                                  'budget': float(budget), 'target_size': int(sms_delivered)})
        print(f"[{camp_id}] {camp_name} is already processed. Updated conv/roi. Skipping heavy attribution...", flush=True)
        continue

    if not branch:
        branch = resolve_branch_dynamic(camp_name)
        if branch:
            _update_if_changed(camp, {'branch_code': branch})

    print(f"\n[{camp_id}] {camp_name} | {camp['type']} | {start_dt}→{end_dt} | branch={branch} | SMS Delivered={sms_delivered}", flush=True)

    branch_cond = f"branch = '{branch}'"
    if "mavoor road" in camp_name.lower():
        branch_cond = "branch IN ('KIN', 'LAN', 'MAH', 'PCT', 'PUT', 'SBM', 'CAM')"
    branch_filter = f"AND {branch_cond}" if branch or "mavoor road" in camp_name.lower() else ""

    # ATTRIBUTION: one ClickHouse query finds the store/state purchasers in the date window
    # who are ALSO in this campaign's customer list (the campaign_customers table is in ClickHouse too).
    cust_subq = (f"SELECT customer_mobile FROM {T_CUST} "
                 f"WHERE source_db = '{SRC}' AND campaign_id = {int(camp_id)}")
    print(f"  Matching store purchasers in ClickHouse ({start_dt} to {end_dt})...", flush=True)
    sql_purchasers = (f"SELECT customer_mobile, SUM(invoice_total) as customer_total "
                      f"FROM azure_invoice_report "
                      f"WHERE toDate(date) >= '{start_dt}' AND toDate(date) <= '{end_dt}' {branch_filter} "
                      f"AND customer_mobile IN ({cust_subq}) "
                      f"GROUP BY customer_mobile "
                      f"HAVING customer_total > 0")
    try:
        purchasers = ch_db.query(sql_purchasers, timeout=180)
    except Exception as e:
        # Never write zero KPIs because of a transient ClickHouse failure - retry next cycle
        print(f"  ClickHouse ERROR (skipping campaign this cycle): {e}", flush=True)
        continue
    purchaser_map = {r['customer_mobile']: float(r.get('customer_total', 0) or 0) for r in purchasers if r.get('customer_mobile')}
    matched_mobiles = set(purchaser_map.keys())

    # Check history (New vs Repeat) only for the matched purchasers
    repeat_customers = set()
    matched_list = list(matched_mobiles)
    for j in range(0, len(matched_list), 10000):
        ch = matched_list[j:j+10000]
        m_str = ", ".join(f"'{m}'" for m in ch)
        hist_sql = (f"SELECT DISTINCT customer_mobile FROM azure_invoice_report "
                    f"WHERE customer_mobile IN ({m_str}) "
                    f"  AND toDate(date) >= '2020-01-01' AND toDate(date) < '{start_dt}'")
        for r in query_clickhouse(hist_sql):
            repeat_customers.add(r.get('customer_mobile'))

    purchase_count = len(matched_mobiles)
    total_revenue = sum(purchaser_map[m] for m in matched_mobiles)
    existing_customers = len(repeat_customers)
    new_customers = purchase_count - existing_customers

    # Use SMS Delivered as audience denominator
    conv_rate = (purchase_count / sms_delivered * 100) if sms_delivered > 0 else 0
    # ROI = Revenue / Actual Cost (how many ₹ returned per ₹ spent)
    roi = (total_revenue / budget) if budget > 0 else 0

    print(f"  -> Rev=Rs.{total_revenue:,.0f} | Customers={purchase_count} (New: {new_customers}, Existing: {existing_customers}) | Conv={conv_rate:.2f}% | ROI={roi:.2f}x", flush=True)

    # Fetch top brands & top categories
    top_brands = []
    top_cats = []
    try:
        inv_filter = f"toDate(s.date) >= '{start_dt}' AND toDate(s.date) <= '{end_dt}'"
        b_cond_ch = f"AND s.branch = '{branch}'" if branch else ""
        if "mavoor road" in camp_name.lower():
            b_cond_ch = "AND s.branch IN ('KIN', 'LAN', 'MAH', 'PCT', 'PUT', 'SBM', 'CAM')"
        
        b_sql = f"""
        SELECT coalesce(nullIf(trim(im.brand), ''), 'Unknown') AS brand,
               SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
               SUM(if(toFloat64(s.sold_price) < 0, -toInt64(s.qty), toInt64(s.qty))) as qty
        FROM azure_sales_report s
        JOIN item_master im ON s.item_code = im.item_code
        WHERE {inv_filter} {b_cond_ch}
          AND im.product != 'AC OUTDOOR' AND im.product != 'SCHEME'
        GROUP BY brand ORDER BY revenue DESC LIMIT 5
        """
        top_brands = [{'brand': r.get('brand',''), 'revenue': float(r.get('revenue',0)), 'qty': int(r.get('qty',0))} for r in query_clickhouse(b_sql)]

        c_sql = f"""
        SELECT coalesce(nullIf(trim(im.product), ''), 'Unknown') AS category,
               SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
               SUM(if(toFloat64(s.sold_price) < 0, -toInt64(s.qty), toInt64(s.qty))) as qty
        FROM azure_sales_report s
        JOIN item_master im ON s.item_code = im.item_code
        WHERE {inv_filter} {b_cond_ch}
          AND im.product != 'AC OUTDOOR' AND im.product != 'SCHEME'
        GROUP BY category ORDER BY revenue DESC LIMIT 5
        """
        top_cats = [{'category': r.get('category',''), 'revenue': float(r.get('revenue',0)), 'qty': int(r.get('qty',0))} for r in query_clickhouse(c_sql)]
    except Exception as e_bc:
        print(f"  Brand/Cat fetch error: {e_bc}", flush=True)

    ch_db.update_campaign(camp_id, {
        'purchase_count': purchase_count, 'purchase_value': total_revenue,
        'conversion_rate': conv_rate, 'roi': roi, 'budget': budget, 'branch_code': branch,
        'new_customers': new_customers, 'existing_customers': existing_customers,
        'top_brands': json.dumps(top_brands), 'top_categories': json.dumps(top_cats),
    })
    print(f"  ✅ Updated.", flush=True)

print("\n=== DONE ===", flush=True)
