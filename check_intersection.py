import sqlite3
import urllib.request
import json
import base64

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM campaign_customers WHERE campaign_id=31325')
print('Total target customers in DB:', c.fetchone()[0])

CH_URL = 'https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/'
auth = base64.b64encode(b'default:ZFlujj9SA_Iei').decode()

sql = "SELECT count() FROM azure_sales_report WHERE BILL_DATE >= '2026-09-03' AND BILL_DATE <= '2026-09-06' AND BRANCH_CODE = 'KTF'"
req = urllib.request.Request(CH_URL, data=(sql + ' FORMAT JSON').encode(), headers={'Authorization': 'Basic '+auth, 'Content-Type': 'text/plain'})
res = urllib.request.urlopen(req)
print('Total purchases in KTF during dates:', json.loads(res.read().decode())['data'][0]['count()'])

# Now let's see how many of the target customers actually purchased
sql2 = """
SELECT count() FROM azure_sales_report 
WHERE BILL_DATE >= '2026-09-03' AND BILL_DATE <= '2026-09-06' 
AND BRANCH_CODE = 'KTF'
AND CUSTOMER_MOBILE IN (
    SELECT number FROM (
        -- We will just pass some numbers to test if ANY exist
"""

c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31325')
mobiles = [r[0] for r in c.fetchall()]
print(f"Sample of mobiles: {mobiles[:5]}")

import urllib.parse
# Test intersection logic in clickhouse by passing in a chunk of 10000 mobiles
chunk = mobiles[:10000]
mob_str = ",".join([f"'{m}'" for m in chunk if m])
sql3 = f"SELECT count() FROM azure_sales_report WHERE BILL_DATE >= '2026-09-03' AND BILL_DATE <= '2026-09-06' AND CUSTOMER_MOBILE IN ({mob_str}) FORMAT JSON"
try:
    req3 = urllib.request.Request(CH_URL, data=sql3.encode(), headers={'Authorization': 'Basic '+auth, 'Content-Type': 'text/plain'})
    res3 = urllib.request.urlopen(req3)
    print("Purchases by first 10k campaign customers:", json.loads(res3.read().decode())['data'][0]['count()'])
except Exception as e:
    print(e)
