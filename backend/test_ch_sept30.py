import urllib.request, json, base64

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def query_clickhouse(sql):
    req = urllib.request.Request(CH_URL)
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode())
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode()).get('data', [])

# Total store purchasers on Sept 30, 2026
data = query_clickhouse("""
    SELECT count(DISTINCT customer_mobile) as unique_customers,
           sum(invoice_total) as total_rev
    FROM azure_invoice_report
    WHERE toDate(date) = '2026-09-30'
""")
print("Sept 30 ClickHouse total:", data)
