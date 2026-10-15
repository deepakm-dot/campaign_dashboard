import http.client
import json
import base64
import sqlite3

# 1. Get campaign customers
conn_db = sqlite3.connect('campaign_dashboard.db')
c = conn_db.cursor()
c.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31325")
mobiles = set([r[0] for r in c.fetchall() if r[0]])
print(f"Loaded {len(mobiles)} campaign customers.")

# 2. Get all customers who bought at KTF between 2026-09-03 and 2026-09-06
CH_URL = "pdhsuv47ec.ap-south-1.aws.clickhouse.cloud"
auth = base64.b64encode(b"default:ZFlujj9SA_Iei").decode()
headers = {"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"}

conn_http = http.client.HTTPSConnection(CH_URL, 8443)
sql = "SELECT distinct customer_mobile FROM azure_invoice_report WHERE branch='KTF' AND date >= '2026-09-03' AND date <= '2026-09-06' FORMAT JSON"
conn_http.request("POST", "/", body=sql, headers=headers)
response = conn_http.getresponse()
data = json.loads(response.read().decode())
ch_mobiles = set([r['customer_mobile'] for r in data['data'] if r['customer_mobile']])
print(f"Loaded {len(ch_mobiles)} customers who bought at KTF.")

# 3. Intersect!
overlap = mobiles.intersection(ch_mobiles)
print(f"OVERLAP: {len(overlap)} customers bought something!")

# 4. What about ALL branches? Did these people buy ANYWHERE?
sql_all = "SELECT distinct customer_mobile FROM azure_invoice_report WHERE date >= '2026-09-03' AND date <= '2026-09-06' FORMAT JSON"
conn_http.request("POST", "/", body=sql_all, headers=headers)
data_all = json.loads(conn_http.getresponse().read().decode())
ch_all_mobiles = set([r['customer_mobile'] for r in data_all['data'] if r['customer_mobile']])
print(f"OVERLAP ALL BRANCHES: {len(mobiles.intersection(ch_all_mobiles))} customers bought something anywhere!")

