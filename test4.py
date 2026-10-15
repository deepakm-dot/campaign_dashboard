import sqlite3, json, urllib.request, base64

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

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31373')
mobiles = [r[0] for r in c.fetchall() if r[0]]

unique_customers = {}
for i in range(0, len(mobiles), 10000):
    chunk = mobiles[i:i+10000]
    m_list = ",".join(f"'{m}'" for m in chunk)
    sql = (f"SELECT customer_mobile, "
           f"SUM(IF(toDate(date) >= '2026-09-17' AND toDate(date) <= '2026-09-20' AND branch IN ('ATF'), invoice_total, 0)) as customer_total, "
           f"MAX(IF(toDate(date) >= '2020-01-01' AND toDate(date) < '2026-09-17', 1, 0)) as has_history "
           f"FROM azure_invoice_report "
           f"WHERE customer_mobile IN ({m_list}) "
           f"GROUP BY customer_mobile "
           f"HAVING customer_total > 0")
    for row in query_clickhouse(sql):
        mob = row.get('customer_mobile', '')
        if mob and mob not in unique_customers:
            unique_customers[mob] = {'has_history': int(row.get('has_history', 0) or 0)}

repeat_mobs = [m for m, v in unique_customers.items() if v['has_history']]
if repeat_mobs:
    m_list2 = ",".join(f"'{m}'" for m in repeat_mobs)
    sql2 = f"SELECT customer_mobile, MIN(date) as min_date, MAX(date) as max_date FROM azure_invoice_report WHERE customer_mobile IN ({m_list2}) AND toDate(date) < '2026-09-17' GROUP BY customer_mobile ORDER BY min_date"
    print("History for Repeat customers (Before Sept 17):")
    for row in query_clickhouse(sql2):
        print(f"  {row['customer_mobile']}: first_purchase={row['min_date']}, last_purchase_before_camp={row['max_date']}")
