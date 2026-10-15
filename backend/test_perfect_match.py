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
    multiIf(
        im.product = 'TV', 'TV',
        im.product = 'WASHING MACHINES', 'Washing machine',
        im.product = 'REFRIGERATORS', 'Referigerator',
        im.product = 'MOBILE', 'Mobile',
        im.product = 'LAPTOP', 'Laptop',
        (im.product = 'AIR CONDITIONER' OR lower(im.item_category) = 'ac indoor')
         AND im.product != 'AC OUTDOOR'
         AND lower(im.item_category) != 'ac outdoor'
         AND lower(im.item_name) NOT LIKE 'o/d%', 'AC',
        'Other'
    ) as product_type,
    count() as line_count,
    sum(toInt64(s.qty)) as total_qty,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
  AND s.branch = 'VPF'
  AND im.product != 'AC OUTDOOR'
  AND lower(im.item_category) != 'ac outdoor'
  AND lower(im.item_name) NOT LIKE 'o/d%'
GROUP BY product_type
ORDER BY total_qty DESC
"""

rows = ch_query(sql)
print("=== PERFECT MATCH RESULTS FOR VPF ===")
for r in rows:
    pt = r['product_type']
    lines = r['line_count']
    qty = r['total_qty']
    rev = r['revenue']
    print(f"{pt:20} | Lines: {lines:4} | Qty: {qty:4} | Revenue: {rev:,.2f}")

tot_q = sum(r['total_qty'] for r in rows)
tot_r = sum(r['revenue'] for r in rows)
print(f"Total: Qty = {tot_q}, Revenue = {tot_r:,.2f}")
