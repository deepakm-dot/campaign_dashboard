"""
Verify campaign KPI values in SQLite against ClickHouse ground truth.
Run from backend/ directory.
"""
import sqlite3, json, urllib.request, base64

DB_FILE = 'campaign_dashboard.db'
CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def ch_query(sql):
    req = urllib.request.Request(CH_URL)
    auth = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', 'Basic ' + auth)
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        res = urllib.request.urlopen(req)
        return json.loads(res.read()).get('data', [])
    except Exception as e:
        print(f"  [CH ERROR] {e}")
        return []

# ---- SQLite: all campaigns ----
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("""
    SELECT id, campaign_name, type, start_date, end_date,
           budget, purchase_count, purchase_value, roi, branch_code
    FROM campaigns
    ORDER BY campaign_name, type
""")
all_camps = [dict(r) for r in cur.fetchall()]
conn.close()

print("=" * 70)
print(f"SQLITE: {len(all_camps)} total campaigns")
print("=" * 70)
for c in all_camps:
    rev  = c['purchase_value'] or 0
    cnt  = c['purchase_count'] or 0
    roi  = c['roi'] or 0
    bgt  = c['budget'] or 0
    if rev > 0 or cnt > 0:
        print(f"  ID={c['id']:4d} | {c['campaign_name'][:35]:35s} | {c['type']:12s} | "
              f"start={c['start_date']} | purchases={cnt:4d} | rev=₹{rev:,.0f} | "
              f"roi=₹{roi:.0f} | budget=₹{bgt:.0f} | branch={c['branch_code']}")

# ---- ClickHouse: get ALL customer mobiles linked to campaigns ----
print("\n" + "=" * 70)
print("CLICKHOUSE: direct revenue check for key campaigns")
print("=" * 70)

# Check Vypin Onam and Paravoor Onam customers in campaign_customers table
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
key_camps = cur.execute("""
    SELECT id, campaign_name, type, start_date, end_date, branch_code, budget
    FROM campaigns
    WHERE campaign_name LIKE '%Onam%'
    ORDER BY campaign_name, type
""").fetchall()
conn.close()

for camp in key_camps:
    cid   = camp['id']
    name  = camp['campaign_name']
    ctype = camp['type']
    start = (camp['start_date'] or '')[:10]
    end   = (camp['end_date']   or start)[:10]
    branch= camp['branch_code'] or ''
    budget= camp['budget'] or 0

    # Get campaign customers from SQLite
    conn2 = sqlite3.connect(DB_FILE)
    conn2.row_factory = sqlite3.Row
    cur2 = conn2.cursor()
    cur2.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?", (cid,))
    mobiles = [r['customer_mobile'] for r in cur2.fetchall()]
    conn2.close()

    print(f"\n  Campaign: {name} [{ctype}] id={cid}")
    print(f"  Dates: {start} → {end}  |  Branch: '{branch}'  |  Budget: ₹{budget:.0f}")
    print(f"  Linked customers in SQLite: {len(mobiles)}")

    if not mobiles:
        print("  ⚠️  NO CUSTOMERS LINKED — ClickHouse revenue cannot be calculated!")
        # Try a direct CH query using branch+dates
        if branch:
            sql = f"""
                SELECT COUNT(DISTINCT customer_mobile) as cust,
                       COUNT(DISTINCT invoice_no) as invoices,
                       SUM(invoice_total) as revenue
                FROM azure_invoice_report
                WHERE toDate(date) >= '{start}' AND toDate(date) <= '{end}'
                  AND branch = '{branch}'
            """
            rows = ch_query(sql)
            if rows:
                r = rows[0]
                print(f"  → ClickHouse ALL customers at branch {branch}: "
                      f"cust={r.get('cust')}, invoices={r.get('invoices')}, "
                      f"rev=₹{float(r.get('revenue',0)):,.0f}")
        continue

    mobile_list = ",".join(f"'{m}'" for m in mobiles[:500])
    sql = f"""
        SELECT COUNT(DISTINCT customer_mobile) as matched_customers,
               COUNT(DISTINCT invoice_no)      as invoices,
               SUM(invoice_total)              as total_revenue
        FROM azure_invoice_report
        WHERE customer_mobile IN ({mobile_list})
          AND toDate(date) >= '{start}'
          AND toDate(date) <= '{end}'
          {("AND branch = '" + branch + "'") if branch else ""}
    """
    rows = ch_query(sql)
    if rows:
        r = rows[0]
        ch_rev = float(r.get('total_revenue', 0) or 0)
        ch_inv = int(r.get('invoices', 0) or 0)
        ch_cust= int(r.get('matched_customers', 0) or 0)
        roi = ch_rev / budget if budget > 0 else 0
        print(f"  ClickHouse: matched_customers={ch_cust}, invoices={ch_inv}, "
              f"revenue=₹{ch_rev:,.0f}, ROI=₹{roi:.0f}")
    else:
        print("  ClickHouse: No data returned")

print("\n" + "=" * 70)
print("Done.")
