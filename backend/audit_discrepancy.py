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

# Check the difference between:
# A: azure_sales_report directly: branch='PAVR', toDate(date) between '2026-08-06' and '2026-08-09'
# B: azure_invoice_report joined with azure_sales_report

sql_compare = """
SELECT
    count() as total_sales_rows,
    countIf(sold_price > 0) as sales_gt_0,
    countIf(sold_price = 0) as sales_eq_0,
    sum(qty) as sum_qty,
    sumIf(qty, sold_price > 0) as sum_qty_gt_0,
    sum(sold_price * qty) as sum_revenue
FROM azure_sales_report
WHERE branch = 'PAVR' AND toDate(date) BETWEEN '2026-08-06' AND '2026-08-09'
"""
print("Direct azure_sales_report:")
print(ch_query(sql_compare))

sql_join = """
SELECT
    count() as total_joined_rows,
    countIf(s.sold_price > 0) as joined_gt_0,
    countIf(s.sold_price = 0) as joined_eq_0,
    sum(s.qty) as sum_qty,
    sumIf(s.qty, s.sold_price > 0) as sum_qty_gt_0,
    sum(s.sold_price * s.qty) as sum_revenue
FROM azure_invoice_report inv
JOIN azure_sales_report s ON s.invoice_no = inv.invoice_no
WHERE inv.branch = 'PAVR' AND toDate(inv.date) BETWEEN '2026-08-06' AND '2026-08-09'
"""
print("\nJoined azure_invoice_report + azure_sales_report:")
print(ch_query(sql_join))

sql_date_mismatch = """
SELECT 
    inv.invoice_no,
    toDate(inv.date) as inv_date,
    inv.branch as inv_branch,
    toDate(s.date) as sales_date,
    s.branch as sales_branch,
    s.sold_price,
    s.item_code
FROM azure_invoice_report inv
JOIN azure_sales_report s ON s.invoice_no = inv.invoice_no
WHERE (inv.branch = 'PAVR' OR s.branch = 'PAVR')
  AND (toDate(inv.date) BETWEEN '2026-08-06' AND '2026-08-09' OR toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09')
  AND (inv.branch != s.branch OR toDate(inv.date) != toDate(s.date))
LIMIT 10
"""
mismatches = ch_query(sql_date_mismatch)
print(f"\nDate or branch mismatches between invoice and sales: {len(mismatches)}")
for m in mismatches:
    print(m)
