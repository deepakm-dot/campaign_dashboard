import urllib.request, json, base64

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def query_ch(sql):
    req = urllib.request.Request(CH_URL)
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode())
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode()).get('data', [])

print("=== 1. RAW azure_sales_report on 2026-09-30 ===")
q1 = """
SELECT 
    count() as row_count,
    sum(toInt64(qty)) as total_qty,
    sum(toFloat64(sold_price) * toInt64(qty)) as total_revenue,
    sum(if(toFloat64(sold_price) > 0, toFloat64(sold_price) * toInt64(qty), 0)) as gross_pos,
    sum(if(toFloat64(sold_price) < 0, toFloat64(sold_price) * toInt64(qty), 0)) as ret_neg
FROM azure_sales_report
WHERE toDate(date) = '2026-09-30'
"""
print(query_ch(q1))

print("\n=== 2. RAW azure_invoice_report on 2026-09-30 ===")
q2 = """
SELECT 
    count() as invoice_count,
    sum(invoice_total) as invoice_revenue
FROM azure_invoice_report
WHERE toDate(date) = '2026-09-30'
"""
print(query_ch(q2))

print("\n=== 3. What does current store-sales query return with item_master filter? ===")
q3 = """
SELECT
    count() as cnt,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) as filtered_revenue,
    sum(if(toFloat64(s.sold_price) > 0, toInt64(s.qty), 0)) as paid_qty,
    sum(if(toFloat64(s.sold_price) < 0, -toInt64(s.qty), toInt64(s.qty))) as net_qty
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE toDate(s.date) = '2026-09-30'
  AND im.product != 'AC OUTDOOR'
  AND lower(im.item_category) != 'ac outdoor'
  AND lower(im.item_name) NOT LIKE 'o/d%'
  AND coalesce(im.product, '') != 'SCHEME'
  AND coalesce(im.item_group, '') != 'SCHEME'
"""
print(query_ch(q3))

print("\n=== 4. Breakdown of items excluded by item_master filters ===")
q4 = """
SELECT 
    coalesce(nullIf(trim(im.product), ''), 'NULL/UNKNOWN') as prod,
    coalesce(nullIf(trim(im.item_category), ''), 'NULL/UNKNOWN') as cat,
    coalesce(nullIf(trim(im.item_group), ''), 'NULL/UNKNOWN') as grp,
    count() as cnt,
    sum(toInt64(s.qty)) as qty,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) as excluded_revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE toDate(s.date) = '2026-09-30'
  AND (
      im.product = 'AC OUTDOOR'
      OR lower(im.item_category) = 'ac outdoor'
      OR lower(im.item_name) LIKE 'o/d%'
      OR coalesce(im.product, '') = 'SCHEME'
      OR coalesce(im.item_group, '') = 'SCHEME'
      OR im.item_code IS NULL
  )
GROUP BY prod, cat, grp
ORDER BY excluded_revenue DESC
"""
print(query_ch(q4))
