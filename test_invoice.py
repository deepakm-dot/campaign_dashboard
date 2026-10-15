import http.client
import json
import base64

CH_URL = "pdhsuv47ec.ap-south-1.aws.clickhouse.cloud"
auth = base64.b64encode(b"default:ZFlujj9SA_Iei").decode()
headers = {"Authorization": "Basic " + auth, "Content-Type": "application/x-www-form-urlencoded"}

conn = http.client.HTTPSConnection(CH_URL, 8443)
sql = "DESCRIBE TABLE azure_invoice_report FORMAT JSON"
conn.request("POST", "/", body=sql, headers=headers)
response = conn.getresponse()
data = json.loads(response.read().decode())
print("Columns:", [r['name'] for r in data['data']])
