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
    res = urllib.request.urlopen(req)
    return json.loads(res.read()).get('data', [])

sql = """
SELECT 
    toDate(s.date) as dt,
    s.invoice_no,
    s.item_code,
    im.product,
    im.item_name,
    s.qty,
    s.sold_price
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF'
  AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND (im.product = 'TV' 
       OR lower(im.item_category) LIKE '%tv%'
       OR lower(im.category) = 'consumer electronics' AND lower(im.product) = 'tv')
ORDER BY dt, s.invoice_no
"""
rows = ch_query(sql)
print(f"Total TV rows in VPF: {len(rows)}")
for r in rows:
    print(f"  {r['dt']} | {r['invoice_no']} | qty={r['qty']} | price={r['sold_price']} | {r['item_name'][:40]}")
