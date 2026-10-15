import urllib.request
import json
import base64
CH_URL = 'https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/'
auth = base64.b64encode(b'default:ZFlujj9SA_Iei').decode()
sql = "SELECT CUSTOMER_MOBILE FROM azure_sales_report WHERE BRANCH_CODE='KTF' AND BILL_DATE >= '2026-09-03' LIMIT 5 FORMAT JSON"
req = urllib.request.Request(CH_URL, data=sql.encode(), headers={'Authorization': 'Basic '+auth, 'Content-Type': 'text/plain'})
res = urllib.request.urlopen(req)
print(json.loads(res.read().decode())['data'])
