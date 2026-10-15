import sqlite3, json, urllib.request, base64

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31369 LIMIT 20000')
mobiles = [r[0] for r in c.fetchall() if r[0]]

def query_clickhouse(sql):
    url = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
    user, pwd = "default", ""
    auth = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    req = urllib.request.Request(
        url,
        data=sql.encode('utf-8'),
        headers={'Authorization': f'Basic {auth}'}
    )
    with urllib.request.urlopen(req) as response:
        return response.read().decode('utf-8')

m_list = ",".join(f"'{m}'" for m in mobiles)

q1 = f"SELECT count(DISTINCT customer_mobile) FROM azure_invoice_report WHERE customer_mobile IN ({m_list}) AND toDate(date) >= '2026-09-12' AND toDate(date) <= '2026-09-13'"
print('Matches 12-13 Sept:', query_clickhouse(q1).strip())

q2 = f"SELECT count(DISTINCT customer_mobile) FROM azure_invoice_report WHERE customer_mobile IN ({m_list})"
print('Matches all time:', query_clickhouse(q2).strip())
