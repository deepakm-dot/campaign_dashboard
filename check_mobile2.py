import urllib.request
import urllib.parse
import json
import base64

CH_URL = 'https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/'
auth = base64.b64encode(b'default:ZFlujj9SA_Iei').decode()

sql = "SELECT CUSTOMER_MOBILE FROM azure_sales_report WHERE BRANCH_CODE='KTF' AND BILL_DATE >= '2026-09-03' AND BILL_DATE <= '2026-09-06' LIMIT 10 FORMAT JSON"
url = CH_URL + "?query=" + urllib.parse.quote(sql)

req = urllib.request.Request(url, headers={'Authorization': 'Basic '+auth})
res = urllib.request.urlopen(req)
print("POS mobiles:", json.loads(res.read().decode())['data'])

import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31325 LIMIT 10')
print("Campaign DB mobiles:", [r[0] for r in c.fetchall()])
