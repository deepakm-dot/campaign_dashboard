"""
Direct KPI calculation for Vypin WA (1235) and Paravoor WA (1234).
Queries ClickHouse with the customer mobiles and updates campaigns table.
"""
import sqlite3, json, urllib.request, base64, re, sys
sys.stdout.reconfigure(line_buffering=True)

DB_FILE = 'campaign_dashboard.db'
CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

BRANCH_MAP = {'vypin': 'VPF', 'paravoor': 'PAVR'}

def query_clickhouse(sql):
    req = urllib.request.Request(CH_URL)
    token = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', 'Basic ' + token)
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode()).get('data', [])
    except Exception as e:
        print(f"  ClickHouse ERROR: {e}", flush=True)
        return []

conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; c = conn.cursor()

# Get campaigns that have customers
c.execute("""
    SELECT camps.id, camps.campaign_name, camps.type, camps.start_date, camps.end_date,
           camps.budget, camps.branch_code,
           COUNT(cc.id) as cust_count
    FROM campaigns camps
    JOIN campaign_customers cc ON cc.campaign_id = camps.id
    GROUP BY camps.id
""")
camps = c.fetchall()

print(f"=== KPI CALCULATION for {len(camps)} campaigns with customers ===\n", flush=True)

for camp in camps:
    camp_id   = camp['id']
    camp_name = camp['campaign_name']
    start_dt  = camp['start_date']
    end_dt    = camp['end_date'] or start_dt
    budget    = camp['budget'] or 0
    cust_cnt  = camp['cust_count']
    branch    = camp['branch_code'] or ''

    # Auto-detect branch if not set
    if not branch:
        first_word = re.sub(r'[^a-z]', '', camp_name.lower().split()[0])
        branch = BRANCH_MAP.get(first_word, '')

    print(f"[{camp_id}] {camp_name} | {camp['type']} | {start_dt} → {end_dt} | branch={branch} | customers={cust_cnt:,}", flush=True)

    # Get all customer mobiles for this campaign
    c.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?", (camp_id,))
    mobiles = [r[0] for r in c.fetchall() if r[0]]

    if not mobiles:
        print(f"  No mobiles — skipping.", flush=True)
        continue

    # Build branch filter
    branch_cond = f"branch = '{branch}'"
    if "mavoor road" in camp_name.lower():
        branch_cond = "branch IN ('KIN', 'LAN', 'MAH', 'PCT', 'PUT', 'SBM', 'CAM')"
    branch_filter = f"AND {branch_cond}" if branch else ""

    # Query ClickHouse in chunks of 10,000
    chunk_size = 10000
    all_invoices = set()
    total_revenue = 0.0
    print(f"  Querying ClickHouse ({len(mobiles):,} mobiles, {(len(mobiles)-1)//chunk_size+1} chunks)...", flush=True)

    for i in range(0, len(mobiles), chunk_size):
        chunk = mobiles[i:i+chunk_size]
        mobile_list = ", ".join(f"'{m}'" for m in chunk)
        sql = (f"SELECT invoice_no, invoice_total "
               f"FROM azure_invoice_report "
               f"WHERE customer_mobile IN ({mobile_list}) "
               f"AND toDate(date) >= '{start_dt}' AND toDate(date) <= '{end_dt}' "
               f"{branch_filter}")
        rows = query_clickhouse(sql)
        for row in rows:
            inv = row.get('invoice_no','')
            amt = float(row.get('invoice_total', 0) or 0)
            if inv and inv not in all_invoices:
                all_invoices.add(inv)
                total_revenue += amt
        print(f"  Chunk {i//chunk_size+1}: {len(rows)} rows, running invoices={len(all_invoices)}, rev=₹{total_revenue:,.0f}", flush=True)

    purchase_count = len(all_invoices)
    conv_rate = (purchase_count / len(mobiles) * 100) if mobiles else 0
    roi = ((total_revenue - budget) / budget * 100) if budget > 0 else 0

    print(f"  → Revenue: ₹{total_revenue:,.0f} | Invoices: {purchase_count} | Conv: {conv_rate:.2f}% | ROI: {roi:.0f}%", flush=True)

    # --- Brand/category breakdown ---
    top_brands_json = '[]'; top_cats_json = '[]'
    if mobiles and all_invoices:
        inv_list = ", ".join(f"'{inv}'" for inv in list(all_invoices)[:5000])
        brand_sql = (f"SELECT im.brand, SUM(s.qty * s.rate) as total "
                     f"FROM azure_sales_report s "
                     f"JOIN item_master im ON s.item_code = im.item_code "
                     f"WHERE s.invoice_no IN ({inv_list}) {branch_filter} "
                     f"GROUP BY im.brand ORDER BY total DESC LIMIT 10")
        brand_rows = query_clickhouse(brand_sql)
        top_brands_json = json.dumps([{"brand": r.get('brand',''), "total": float(r.get('total',0))} for r in brand_rows])

    # Update campaigns table
    c.execute("""
        UPDATE campaigns SET
          target_size=?, purchase_count=?, purchase_value=?,
          conversion_rate=?, roi=?, budget=?,
          top_brands=?, top_categories=?, branch_code=?
        WHERE id=?
    """, (len(mobiles), purchase_count, total_revenue,
          conv_rate, roi, budget,
          top_brands_json, top_cats_json, branch, camp_id))
    conn.commit()
    print(f"  ✅ Updated campaigns table for [{camp_id}].", flush=True)

print("\n=== DONE — Dashboard should now reflect correct data ===", flush=True)
conn.close()
