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

# Let's inspect the exact invoices/rows that make up:
# 2026-08-06: 198 items, 1,521,968.47
# 2026-08-07: 197 items, 892,704.76
# 2026-08-08: 204 items, 1,380,373.66
# 2026-08-09: 215 items, 1,572,409.80

sql = """
SELECT 
    toDate(date) as dt,
    count() as all_rows,
    countIf(sold_price > 0) as pos_price_rows,
    countIf(sold_price = 0) as zero_price_rows,
    countIf(sold_price < 0) as neg_price_rows,
    sumIf(qty, sold_price > 0) as sum_qty_pos,
    sumIf(qty, sold_price = 0) as sum_qty_zero,
    sumIf(qty, sold_price < 0) as sum_qty_neg,
    sumIf(sold_price * qty, sold_price > 0) as sum_amt_pos,
    sumIf(sold_price * qty, sold_price < 0) as sum_amt_neg
FROM azure_sales_report
WHERE branch = 'PAVR' AND toDate(date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY dt
ORDER BY dt
"""
for r in ch_query(sql):
    print(r)
