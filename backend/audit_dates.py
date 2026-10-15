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

print("=== Check date timestamps on 2026-09-30 ===")
print(query_ch("SELECT min(date) as min_ts, max(date) as max_ts, count() as cnt FROM azure_sales_report WHERE toDate(date) = '2026-09-30'"))

print("\n=== Check date range around 2026-09-30 ===")
print(query_ch("""
SELECT toDate(date) as dt, count() as cnt, sum(toFloat64(sold_price) * toInt64(qty)) as rev
FROM azure_sales_report
WHERE toDate(date) >= '2026-09-29' AND toDate(date) <= '2026-10-01'
GROUP BY dt ORDER BY dt
"""))
