import json, urllib.request, base64

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

print("="*80)
print("1. BRANCH CHECK: Any branch with 'PAR' or 'PVR' or 'PAV' in azure_invoice_report:")
rows = ch_query("""
    SELECT DISTINCT branch, COUNT() as invoices
    FROM azure_invoice_report
    WHERE lower(branch) LIKE '%par%' 
       OR lower(branch) LIKE '%pav%' 
       OR lower(branch) LIKE '%pvr%'
    GROUP BY branch
    ORDER BY invoices DESC
""")
for r in rows:
    print(r)

print("="*80)
print("2. Check if any branch name or location table exists in ClickHouse:")
tables = ch_query("SHOW TABLES")
print("Tables in ClickHouse:", [t.get('name') for t in tables])

print("="*80)
print("3. Check branch column and any branch description / branch master table:")
for t in tables:
    tname = t.get('name')
    if 'branch' in tname.lower() or 'store' in tname.lower():
        print(f"Table {tname}:")
        cols = ch_query(f"DESCRIBE {tname}")
        print([c.get('name') for c in cols])
