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

print("=== Check invoice prefixes on 2026-09-30 ===")
q = """
SELECT 
    substring(invoice_no, 1, 3) as pfx,
    count() as cnt,
    sum(toInt64(qty)) as qty,
    sum(toFloat64(sold_price) * toInt64(qty)) as rev
FROM azure_sales_report
WHERE toDate(date) = '2026-09-30'
GROUP BY pfx
ORDER BY rev DESC
"""
print(query_ch(q))

print("\n=== Check date ranges / timestamps on 2026-09-30 in ClickHouse ===")
q_date = """
SELECT 
    min(date) as min_ts,
    max(date) as max_ts,
    count() as cnt
FROM azure_sales_report
WHERE toDate(date) = '2026-09-30'
"""
print(query_ch(q_date))

print("\n=== Check next day early morning or UTC offsets ===")
q_utc = """
SELECT 
    toDate(date) as dt,
    count() as cnt,
    sum(toFloat64(sold_price) * toInt64(qty)) as rev
FROM azure_sales_report
WHERE date >= '2026-09-30 00:00:00' AND date <= '2026-10-01 06:00:00'
GROUP BY dt
ORDER BY dt
"""
print(query_ch(q_utc))
