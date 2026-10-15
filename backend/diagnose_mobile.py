"""
Deep diagnose: check mobile number format in campaign_customers vs ClickHouse.
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

# Get sample mobiles from campaign_customers for Vypin (id=732)
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=732 LIMIT 20")
sqlite_mobiles = [r['customer_mobile'] for r in cur.fetchall()]
conn.close()

print("SAMPLE MOBILES IN SQLite (campaign_customers, Vypin id=732):")
for m in sqlite_mobiles[:10]:
    print(f"  '{m}'  len={len(m)}")

# Get sample mobiles from ClickHouse azure_invoice_report for Aug 6-9
print("\nSAMPLE MOBILES IN ClickHouse (azure_invoice_report, Aug 6-9):")
ch_rows = ch_query("""
    SELECT DISTINCT customer_mobile
    FROM azure_invoice_report
    WHERE toDate(date) >= '2026-08-06' AND toDate(date) <= '2026-08-09'
    LIMIT 20
""")
for r in ch_rows[:10]:
    m = r.get('customer_mobile', '')
    print(f"  '{m}'  len={len(m)}")

# Now try matching: use last-10-digits normalization
print("\nTEST: Normalizing SQLite mobiles to last 10 digits and checking CH:")
norm_sqlite = set()
for m in sqlite_mobiles:
    digits = ''.join(c for c in str(m) if c.isdigit())
    if len(digits) >= 10:
        norm_sqlite.add(digits[-10:])

print(f"  Normalized SQLite sample ({len(norm_sqlite)} unique 10-digit):")
sample_norm = list(norm_sqlite)[:10]
for m in sample_norm:
    print(f"  '{m}'")

if sample_norm:
    in_list = ",".join(f"'{m}'" for m in sample_norm)
    # Check exact match
    rows1 = ch_query(f"""
        SELECT COUNT(*) as cnt FROM azure_invoice_report
        WHERE customer_mobile IN ({in_list})
          AND toDate(date) >= '2026-08-06' AND toDate(date) <= '2026-08-09'
    """)
    print(f"  Exact match in CH: {rows1[0].get('cnt',0) if rows1 else 0}")

    # Check with substring
    rows2 = ch_query(f"""
        SELECT customer_mobile FROM azure_invoice_report
        WHERE toDate(date) >= '2026-08-06' AND toDate(date) <= '2026-08-09'
        LIMIT 5
    """)
    if rows2:
        ch_sample = rows2[0].get('customer_mobile','')
        print(f"\n  CH raw mobile example: '{ch_sample}' len={len(ch_sample)}")
        ch_digits = ''.join(c for c in ch_sample if c.isdigit())
        print(f"  CH digits only: '{ch_digits}' len={len(ch_digits)}")
        last10 = ch_digits[-10:] if len(ch_digits) >= 10 else ch_digits
        print(f"  CH last 10: '{last10}'  in sqlite_norm? {last10 in norm_sqlite}")

# Now check: what are the stored purchase_value & purchase_count for id=731,732?
conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT id, campaign_name, type, purchase_count, purchase_value, roi, budget FROM campaigns WHERE id IN (731,732,738,739)")
for r in cur.fetchall():
    d = dict(r)
    print(f"\nSQLite stored: id={d['id']} {d['campaign_name']} [{d['type']}] "
          f"purchases={d['purchase_count']} rev=₹{d['purchase_value']:,.0f} roi=₹{d['roi']:.0f}")
conn.close()
