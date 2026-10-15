import requests
import json
import base64

CH_URL = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"
auth = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()

sql = "SELECT CUSTOMER_MOBILE FROM azure_sales_report WHERE BRANCH_CODE='KTF' AND BILL_DATE >= '2026-09-03' LIMIT 5 FORMAT JSON"

try:
    res = requests.post(CH_URL, headers={'Authorization': 'Basic ' + auth}, data=sql)
    print("Status:", res.status_code)
    print("Response:", res.text)
except Exception as e:
    print("Error:", e)
