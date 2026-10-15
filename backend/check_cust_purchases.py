import json, urllib.request, base64, sqlite3

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

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=731")
mobiles = [r[0] for r in c.fetchall() if r[0]]
print(f"Campaign 731 has {len(mobiles)} target customer mobiles.")

# Check in ClickHouse where these mobiles purchased between Aug 6 and Aug 9:
# Clean mobiles to last 10 digits
clean_mobiles = []
for m in mobiles:
    m_clean = ''.join(filter(str.isdigit, str(m)))
    if len(m_clean) >= 10:
        clean_mobiles.append(m_clean[-10:])

clean_mobiles = list(set(clean_mobiles))
print(f"Unique 10-digit mobiles: {len(clean_mobiles)}")

# Query ClickHouse for purchases by these mobiles Aug 6-9
mobiles_str = "','".join(clean_mobiles[:1000]) # take chunk
sql = f"""
    SELECT inv.branch, count() as cnt, sum(toFloat64(inv.net_amount)) as rev
    FROM azure_invoice_report inv
    WHERE right(inv.mobile, 10) IN ('{mobiles_str}')
      AND toDate(inv.date) >= '2026-08-06'
      AND toDate(inv.date) <= '2026-08-09'
    GROUP BY inv.branch
    ORDER BY rev DESC
"""
rows = ch_query(sql)
print("Branches where campaign customers purchased:")
for r in rows:
    print(r)
