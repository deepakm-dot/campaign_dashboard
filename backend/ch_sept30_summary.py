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

# 1. azure_sales_report total
s1 = query_ch("""
SELECT 
    count() as total_rows,
    sum(toInt64(qty)) as total_units_sold,
    count(DISTINCT branch) as total_stores,
    sum(toFloat64(sold_price) * toInt64(qty)) as net_revenue,
    sum(if(toFloat64(sold_price) > 0, toFloat64(sold_price) * toInt64(qty), 0)) as gross_sales,
    sum(if(toFloat64(sold_price) < 0, toFloat64(sold_price) * toInt64(qty), 0)) as returns_deductions
FROM azure_sales_report
WHERE toDate(date) = '2026-09-30'
""")
print("1. azure_sales_report:", s1)

# 2. azure_invoice_report total
s2 = query_ch("""
SELECT 
    count() as total_invoices,
    count(DISTINCT customer_mobile) as total_unique_customers,
    count(DISTINCT branch) as total_stores,
    sum(invoice_total) as total_invoice_revenue
FROM azure_invoice_report
WHERE toDate(date) = '2026-09-30'
""")
print("2. azure_invoice_report:", s2)

# 3. Product breakdown from azure_sales_report
s3 = query_ch("""
SELECT 
    coalesce(nullIf(trim(im.product), ''), 'Other/Uncategorized') as product,
    sum(toInt64(s.qty)) as qty,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE toDate(s.date) = '2026-09-30'
GROUP BY product
ORDER BY revenue DESC
""")
print("3. Product breakdown:")
for r in s3:
    print(f"   {r['product']}: Qty={r['qty']:,}, Revenue=Rs.{float(r['revenue']):,.2f}")
