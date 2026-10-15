import sqlite3
import base64
import json
import urllib.request
import urllib.parse

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31325 LIMIT 1000')
mobiles = [r[0] for r in c.fetchall()]

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def query_clickhouse(sql):
    req = urllib.request.Request(CH_URL)
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode())
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode()).get('data', [])
    except Exception as e:
        print(f"  ClickHouse ERROR: {e}", flush=True); return []

# 1. Let's see what a sample of ClickHouse mobile numbers looks like!
print("ClickHouse sample:")
print(query_clickhouse("SELECT CUSTOMER_MOBILE FROM azure_sales_report WHERE BRANCH_CODE='KTF' AND BILL_DATE >= '2026-09-03' LIMIT 5"))

# 2. Check if appending 91 fixes it
mobiles_91 = ["91" + m for m in mobiles]
sql = f"""
SELECT sum(NET_VALUE), count(distinct CUSTOMER_MOBILE) 
FROM azure_sales_report
WHERE BRANCH_CODE='KTF' 
AND BILL_DATE >= '2026-09-03' AND BILL_DATE <= '2026-09-06'
AND CUSTOMER_MOBILE IN ({','.join("'" + m + "'" for m in mobiles_91)})
"""
print("With 91 prefix:", query_clickhouse(sql))

# 3. Check with +91 prefix
mobiles_plus91 = ["+91" + m for m in mobiles]
sql = f"""
SELECT sum(NET_VALUE), count(distinct CUSTOMER_MOBILE) 
FROM azure_sales_report
WHERE BRANCH_CODE='KTF' 
AND BILL_DATE >= '2026-09-03' AND BILL_DATE <= '2026-09-06'
AND CUSTOMER_MOBILE IN ({','.join("'" + m + "'" for m in mobiles_plus91)})
"""
print("With +91 prefix:", query_clickhouse(sql))
