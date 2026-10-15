import urllib.request, json, base64

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def query_ch(sql):
    req = urllib.request.Request(CH_URL)
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode())
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode()).get('data', [])
    except urllib.error.HTTPError as e:
        print("ClickHouse error:", e.read().decode())
        return []

print("=== Check qty vs sold_price signs ===")
q = """
SELECT 
    countIf(qty > 0 AND sold_price > 0) as pos_pos_cnt,
    sumIf(sold_price * qty, qty > 0 AND sold_price > 0) as pos_pos_rev,
    sumIf(qty, qty > 0 AND sold_price > 0) as pos_pos_qty,
    
    countIf(qty > 0 AND sold_price < 0) as pos_neg_cnt,
    sumIf(sold_price * qty, qty > 0 AND sold_price < 0) as pos_neg_rev,
    sumIf(qty, qty > 0 AND sold_price < 0) as pos_neg_qty,

    countIf(qty < 0 AND sold_price > 0) as neg_pos_cnt,
    sumIf(sold_price * qty, qty < 0 AND sold_price > 0) as neg_pos_rev,
    sumIf(qty, qty < 0 AND sold_price > 0) as neg_pos_qty,

    countIf(qty < 0 AND sold_price < 0) as neg_neg_cnt,
    sumIf(sold_price * qty, qty < 0 AND sold_price < 0) as neg_neg_rev,
    sumIf(qty, qty < 0 AND sold_price < 0) as neg_neg_qty,

    countIf(sold_price = 0) as zero_price_cnt,
    sumIf(qty, sold_price = 0) as zero_price_qty
FROM azure_sales_report
WHERE toDate(date) = '2026-09-30'
"""
print(query_ch(q))

print("\n=== Check taxable vs sold_price * qty ===")
q_tax = """
SELECT 
    sum(toFloat64(taxable)) as sum_taxable,
    sum(toFloat64(sold_price) * toInt64(qty)) as sum_sold_price,
    sum(toFloat64(mop) * toInt64(qty)) as sum_mop,
    sum(toFloat64(discount)) as sum_discount
FROM azure_sales_report
WHERE toDate(date) = '2026-09-30'
"""
print(query_ch(q_tax))
