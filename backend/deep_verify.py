"""
Find out: are these campaign customers in ClickHouse at all?
And what date range is the ClickHouse data for?
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
        print(f"[CH ERROR] {e}")
        return []

# Get 50 mobiles from Vypin (id=732)
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=732 LIMIT 50")
mobiles = [r['customer_mobile'] for r in cur.fetchall()]
conn.close()

in_list = ",".join(f"'{m}'" for m in mobiles)

# Q1: Are these mobiles in ClickHouse AT ALL (any date)?
rows = ch_query(f"""
    SELECT COUNT(DISTINCT customer_mobile) as cnt,
           MIN(toDate(date)) as earliest,
           MAX(toDate(date)) as latest,
           SUM(invoice_total) as total_rev
    FROM azure_invoice_report
    WHERE customer_mobile IN ({in_list})
""")
if rows:
    r = rows[0]
    print(f"Vypin customers in ClickHouse (ANY date): {r.get('cnt',0)}")
    print(f"  Date range: {r.get('earliest')} → {r.get('latest')}")
    print(f"  Total revenue (all time): ₹{float(r.get('total_rev',0) or 0):,.0f}")

# Q2: What does CH have for Aug 6-9 specifically?
rows2 = ch_query(f"""
    SELECT COUNT(DISTINCT customer_mobile) as cnt,
           COUNT(DISTINCT invoice_no) as invoices,
           SUM(invoice_total) as rev
    FROM azure_invoice_report
    WHERE customer_mobile IN ({in_list})
      AND toDate(date) >= '2026-08-06'
      AND toDate(date) <= '2026-08-09'
""")
if rows2:
    r = rows2[0]
    print(f"\nVypin customers in ClickHouse (Aug 6-9): {r.get('cnt',0)}")
    print(f"  Invoices: {r.get('invoices',0)}")
    print(f"  Revenue: ₹{float(r.get('rev',0) or 0):,.0f}")

# Q3: Try a wider window Aug 6-12
rows3 = ch_query(f"""
    SELECT COUNT(DISTINCT customer_mobile) as cnt,
           COUNT(DISTINCT invoice_no) as invoices,
           SUM(invoice_total) as rev,
           MIN(toDate(date)) as mn, MAX(toDate(date)) as mx
    FROM azure_invoice_report
    WHERE customer_mobile IN ({in_list})
      AND toDate(date) >= '2026-08-01'
      AND toDate(date) <= '2026-08-31'
""")
if rows3:
    r = rows3[0]
    print(f"\nVypin customers in ClickHouse (Aug 1-31): {r.get('cnt',0)}")
    print(f"  Invoices: {r.get('invoices',0)}")
    print(f"  Revenue: ₹{float(r.get('rev',0) or 0):,.0f}")
    print(f"  Actual dates: {r.get('mn')} → {r.get('mx')}")

# Q4: Check what the billing table in SQLite has for these mobiles
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute(f"""
    SELECT COUNT(*) as cnt, SUM(net_value) as rev,
           MIN(bill_date) as mn, MAX(bill_date) as mx
    FROM billing
    WHERE customer_mobile IN ({in_list})
""")
r = dict(cur.fetchone())
print(f"\nSQLite billing table for Vypin customers: cnt={r['cnt']}, rev=₹{(r['rev'] or 0):,.0f}")
print(f"  Date range: {r['mn']} → {r['mx']}")

# Q5: What's the current stored value (ground truth from earlier calculation)
conn2 = sqlite3.connect(DB_FILE)
conn2.row_factory = sqlite3.Row
cur2 = conn2.cursor()
cur2.execute("SELECT purchase_count, purchase_value, roi, budget FROM campaigns WHERE id=732")
d = dict(cur2.fetchone())
conn2.close()
print(f"\nSQLite stored KPIs for Vypin (id=732):")
print(f"  purchases={d['purchase_count']}  revenue=₹{d['purchase_value']:,.0f}  roi=₹{d['roi']:.0f}  budget=₹{d['budget']:.0f}")

# Q6: Check ClickHouse date range in azure_invoice_report
rows6 = ch_query("""
    SELECT MIN(toDate(date)) as mn, MAX(toDate(date)) as mx,
           COUNT(DISTINCT customer_mobile) as cust
    FROM azure_invoice_report
""")
if rows6:
    r = rows6[0]
    print(f"\nClickHouse azure_invoice_report full range:")
    print(f"  Dates: {r.get('mn')} → {r.get('mx')}  |  Customers: {r.get('cust')}")
