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
    coalesce(im.product, 'NO_PRODUCT') as prod,
    count() as lines,
    sum(s.qty) as units,
    sum(s.sold_price * s.qty) as gross_rev,
    sum(s.taxable) as taxable_rev
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND s.sold_price > 0
GROUP BY prod
ORDER BY gross_rev DESC
"""
rows = ch_query(sql)
for r in rows:
    p = r['prod']
    l = r['lines']
    u = int(r['units'])
    rev = float(r['gross_rev'])
    print(f"{p:25s} | lines: {l:4d} | units: {u:4d} | rev: Rs {rev:12,.2f}")
