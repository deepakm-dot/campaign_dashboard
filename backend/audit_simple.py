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
    try:
        res = urllib.request.urlopen(req)
        return json.loads(res.read()).get('data', [])
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.read().decode('utf-8'))
        return []

sql = """
SELECT 
    toDate(date) as dt,
    count() as lines,
    sum(qty) as qty,
    sum(sold_price * qty) as amount
FROM azure_sales_report
WHERE branch = 'PAVR' AND toDate(date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY dt
ORDER BY dt
"""
for r in ch_query(sql):
    print(r)
