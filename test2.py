import sqlite3, json, urllib.request, base64

def query_clickhouse(sql):
    url = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
    auth = base64.b64encode(b"default:").decode()
    req = urllib.request.Request(url, data=sql.encode('utf-8'), headers={'Authorization': f'Basic {auth}'})
    try:
        with urllib.request.urlopen(req) as resp:
            return [json.loads(line) for line in resp.read().decode('utf-8').strip().split('\n') if line]
    except Exception as e:
        print("ERR:", e)
        return []

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31369')
mobiles = [r[0] for r in c.fetchall() if r[0]]

found = set()
for i in range(0, len(mobiles), 10000):
    chunk = mobiles[i:i+10000]
    m_list = ",".join(f"'{m}'" for m in chunk)
    # Just query any invoice in September 2026
    sql = f"SELECT DISTINCT customer_mobile FROM azure_invoice_report WHERE customer_mobile IN ({m_list}) AND toDate(date) >= '2026-09-01' AND toDate(date) <= '2026-09-30' FORMAT JSONEachRow"
    res = query_clickhouse(sql)
    for r in res:
        found.add(r['customer_mobile'])
        
print("Matches in all of September:", len(found))

found_12_13 = set()
for i in range(0, len(mobiles), 10000):
    chunk = mobiles[i:i+10000]
    m_list = ",".join(f"'{m}'" for m in chunk)
    sql = f"SELECT DISTINCT customer_mobile FROM azure_invoice_report WHERE customer_mobile IN ({m_list}) AND toDate(date) >= '2026-09-12' AND toDate(date) <= '2026-09-13' FORMAT JSONEachRow"
    res = query_clickhouse(sql)
    for r in res:
        found_12_13.add(r['customer_mobile'])
        
print("Matches just 12-13 Sep:", len(found_12_13))
