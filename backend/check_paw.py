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

print("=== Invoices in PAW between Aug 6-9 ===")
rows = ch_query("""
    SELECT count() as cnt
    FROM azure_invoice_report
    WHERE branch = 'PAW'
      AND toDate(date) >= '2026-08-06'
      AND toDate(date) <= '2026-08-09'
""")
print(rows)

print("\n=== Check total invoices across all branches for Paravoor customers in campaign ===")
