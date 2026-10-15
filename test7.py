import json, urllib.request, base64

def query_clickhouse(sql):
    url = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
    auth = base64.b64encode(b"default:ZFlujj9SA_Iei").decode()
    req = urllib.request.Request(url, data=(sql + " FORMAT JSON").encode('utf-8'), headers={'Authorization': f'Basic {auth}'})
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))['data']
    except Exception as e:
        print("ERR:", e)
        return []

sql = """
        SELECT
            toDate(s.date) AS day_date,
            toDayOfWeek(toDate(s.date)) AS dow,
            count(*) AS bills,
            SUM(toInt64(s.qty)) AS units,
            round(SUM(toFloat64(s.sold_price) * toInt64(s.qty)), 2) AS revenue
        FROM azure_sales_report s
        LEFT JOIN item_master im ON s.item_code = im.item_code
        WHERE s.branch = 'MTF'
          AND (im.product != 'AC OUTDOOR' OR im.product IS NULL)
          AND (
              (toDate(s.date) >= '2026-09-10' AND toDate(s.date) <= '2026-09-13')
              OR (toDate(s.date) >= '2026-09-17' AND toDate(s.date) <= '2026-09-20')
          )
        GROUP BY day_date, dow
        ORDER BY day_date ASC
"""
for row in query_clickhouse(sql):
    print(row)
