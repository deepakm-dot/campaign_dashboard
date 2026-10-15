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
    toDate(s.date) as sale_date,
    im.product,
    im.item_category,
    im.item_name,
    s.qty,
    s.sold_price
FROM azure_sales_report s
JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR' 
  AND toDate(s.date) BETWEEN '2026-08-01' AND '2026-08-31'
  AND (im.product IN ('AIR CONDITIONER', 'AC OUTDOOR', 'REFRIGERATORS', 'WASHING MACHINES')
       OR lower(im.item_category) LIKE '%ac%'
       OR lower(im.item_category) LIKE '%ref%'
       OR lower(im.item_category) LIKE '%wm%'
       OR lower(im.item_category) LIKE '%washing machine%')
  AND s.sold_price > 1000
ORDER BY sale_date
"""
rows = ch_query(sql)
print(f"Total AC / Ref / WM items in PAVR in entire August 2026: {len(rows)}")
for r in rows:
    print(f"  {r['sale_date']} | {r['product']:18s} | {r['item_category']:20s} | {r['item_name'][:40]:40s} | qty={int(r['qty'])} | price=₹{float(r['sold_price']):,.2f}")
