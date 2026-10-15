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

print("=== Check azure_ingestion_log for 2026-09-30 ===")
logs = query_ch("SELECT * FROM azure_ingestion_log WHERE date LIKE '%2026-09-30%' OR file_name LIKE '%09-30%' ORDER BY date DESC LIMIT 10")
print(logs)

print("\n=== Check if there are other date formats or spaces in date in ClickHouse ===")
# In POS row 3, Date was '2026 09 30' with SPACES!
# Let's check if there are rows in ClickHouse where date string had spaces or was not parsed!
print("Total rows around Sept 30 in azure_sales_report:")
q_space = query_ch("""
SELECT 
    countIf(sold_price > 0) as pos_count,
    sumIf(toInt64(qty), sold_price > 0) as pos_qty,
    sumIf(toFloat64(sold_price) * toInt64(qty), sold_price > 0) as pos_rev,
    countIf(sold_price < 0) as neg_count,
    sumIf(toInt64(qty), sold_price < 0) as neg_qty,
    sumIf(toFloat64(sold_price) * toInt64(qty), sold_price < 0) as neg_rev
FROM azure_sales_report
WHERE toDate(date) = '2026-09-30'
""")
print(q_space)
