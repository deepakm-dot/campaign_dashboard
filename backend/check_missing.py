import json, urllib.request, base64

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def ch_query(sql):
    req = urllib.request.Request(CH_URL)
    token = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', 'Basic ' + token)
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()).get('data', [])
    except Exception as e:
        print(f"Error: {e}")
        return []

r = ch_query("""
    SELECT s.invoice_no, s.item_code, s.qty, s.sold_price, s.date
    FROM azure_sales_report s
    LEFT JOIN item_master im ON im.item_code = s.item_code
    WHERE s.branch = 'PAVR'
      AND toDate(s.date) >= '2026-08-06'
      AND toDate(s.date) <= '2026-08-09'
      AND im.item_code = ''
""")
print("Missing item:", r)
