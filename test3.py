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

print(f"Total mobiles: {len(mobiles)}")

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
            unique_customers[mob] = {
                'total': float(row.get('customer_total', 0) or 0),
                'has_history': int(row.get('has_history', 0) or 0)
            }

new = sum(1 for v in unique_customers.values() if not v['has_history'])
repeat = sum(1 for v in unique_customers.values() if v['has_history'])
print(f"Calculated: Total={len(unique_customers)}, New={new}, Repeat={repeat}")

new_mobs = [m for m, v in unique_customers.items() if not v['has_history']]
if new_mobs:
    m_list2 = ",".join(f"'{m}'" for m in new_mobs)
    sql2 = f"SELECT customer_mobile, date, branch, invoice_total FROM azure_invoice_report WHERE customer_mobile IN ({m_list2}) ORDER BY date"
    print("History for New customers:")
    for row in query_clickhouse(sql2):
        print(f"  {row['customer_mobile']}: date={row['date']}, branch={row['branch']}, val={row['invoice_total']}")
