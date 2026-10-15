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

sql = """
SELECT im.item_code, im.item_name, im.item_category, im.category, s.qty, s.sold_price
FROM azure_invoice_report inv
JOIN azure_sales_report s  ON s.invoice_no = inv.invoice_no
JOIN item_master        im ON im.item_code  = s.item_code
WHERE toDate(inv.date) >= '2026-08-06'
  AND toDate(inv.date) <= '2026-08-09'
  AND inv.branch        = 'PAVR'
  AND toFloat64(s.sold_price) > 0
  AND (
       lower(im.item_name) LIKE '%ac%'
    OR lower(im.item_name) LIKE '%air%'
    OR lower(im.item_name) LIKE '%ref%'
    OR lower(im.item_name) LIKE '%fridge%'
    OR lower(im.item_name) LIKE '%wash%'
    OR lower(im.item_name) LIKE '%wm%'
  )
"""
rows = ch_query(sql)
print(f"Any potential items with keywords in item_name: {len(rows)}")
for r in rows:
    print(r)
