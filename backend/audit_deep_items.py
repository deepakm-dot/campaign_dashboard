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

print("=== 1. Inspect the 15 SMART CHOICE items sold (sold_price > 0) ===")
sql_sc = """
SELECT 
    s.invoice_no, s.item_code, s.qty, s.sold_price, im.item_name, im.category, im.item_category, im.product
FROM azure_sales_report s
JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND s.sold_price > 0
  AND (im.product = 'SMART CHOICE' OR lower(im.item_category) = 'smart choice')
"""
for r in ch_query(sql_sc):
    print(r)

print("\n=== 2. Check all Laptops (im.product = 'LAPTOP' OR lower(im.item_category) LIKE '%laptop%') ===")
sql_lap = """
SELECT 
    s.invoice_no, s.item_code, s.qty, s.sold_price, im.item_name, im.category, im.item_category, im.product
FROM azure_sales_report s
JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND s.sold_price > 0
  AND (im.product = 'LAPTOP' OR lower(im.item_category) LIKE '%laptop%')
"""
for r in ch_query(sql_lap):
    print(r)

print("\n=== 3. Check the unmapped item (s.item_code = 'DSP60701') ===")
sql_unmapped = """
SELECT * FROM azure_sales_report s
WHERE s.branch = 'PAVR' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND s.item_code NOT IN (SELECT item_code FROM item_master)
"""
for r in ch_query(sql_unmapped):
    print(r)
