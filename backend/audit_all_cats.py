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
    coalesce(im.category, 'UNKNOWN') as cat,
    coalesce(im.item_category, 'UNKNOWN') as item_cat,
    count() as lines,
    sum(s.qty) as units,
    sum(s.sold_price * s.qty) as gross_rev,
    sum(s.taxable) as taxable_rev
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY cat, item_cat
ORDER BY gross_rev DESC
"""
rows = ch_query(sql)
print(f"{'CATEGORY':25s} | {'ITEM_CATEGORY':25s} | {'LINES':5s} | {'UNITS':5s} | {'GROSS REV':15s}")
print("-" * 85)
for r in rows:
    print(f"{r['cat']:25s} | {r['item_cat']:25s} | {r['lines']:5d} | {int(r['units']):5d} | ₹{float(r['gross_rev']):14,.2f}")
