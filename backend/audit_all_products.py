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

# Let's inspect im.product grouping for VPF
sql_vpf = """
SELECT 
    im.product,
    count() as line_count,
    sum(toInt64(s.qty)) as total_qty,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) as total_revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY im.product
ORDER BY total_qty DESC
"""

print("=== VPF im.product summary ===")
for r in ch_query(sql_vpf):
    print(f"Product: {r['product']:25} | Lines: {r['line_count']:4} | Qty: {r['total_qty']:4} | Revenue: ₹{r['total_revenue']:,.2f}")

print("\n=== PAVR im.product summary ===")
sql_pavr = """
SELECT 
    im.product,
    count() as line_count,
    sum(toInt64(s.qty)) as total_qty,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) as total_revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY im.product
ORDER BY total_qty DESC
"""
for r in ch_query(sql_pavr):
    print(f"Product: {r['product']:25} | Lines: {r['line_count']:4} | Qty: {r['total_qty']:4} | Revenue: ₹{r['total_revenue']:,.2f}")
