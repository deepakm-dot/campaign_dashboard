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

# Check how the POS daily sales report groups transactions for PAVR
# In the screenshot, for each day there are 2 or 3 rows:
# e.g. 2026-08-06 has 3 rows:
# qty -1, amount -8000
# qty 198, amount 1521968.47
# qty 2, amount -5699
# Let's see what distinguishes these rows!

sql = """
SELECT 
    toDate(date) as dt,
    multiIf(
        invoice_no LIKE '%-SR-%' OR sold_price < 0 AND item_code NOT LIKE 'SC%', 'RETURN',
        sold_price < 0 OR item_code LIKE 'SC%', 'EXCHANGE',
        'SALES'
    ) as txn_type,
    count() as cnt,
    sum(qty) as sum_qty,
    sum(sold_price * qty) as sum_amount
FROM azure_sales_report
WHERE branch = 'PAVR' AND toDate(date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY dt, txn_type
ORDER BY dt, txn_type
"""
print("Grouped by txn_type:")
for r in ch_query(sql):
    print(r)

# Also check by invoice prefix (e.g. 26-I-, 26-SR-, 26-EI-)
sql2 = """
SELECT 
    toDate(date) as dt,
    splitByChar('-', invoice_no)[2] as doc_type,
    count() as cnt,
    sum(qty) as sum_qty,
    sum(sold_price * qty) as sum_amount
FROM azure_sales_report
WHERE branch = 'PAVR' AND toDate(date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY dt, doc_type
ORDER BY dt, doc_type
"""
print("\nGrouped by doc_type in invoice_no:")
for r in ch_query(sql2):
    print(r)
