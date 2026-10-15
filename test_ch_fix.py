import sys
sys.path.append('backend')
import fixkpi
data = fixkpi.query_clickhouse("SELECT CUSTOMER_MOBILE FROM azure_sales_report WHERE BRANCH_CODE='KTF' AND BILL_DATE >= '2026-09-03' LIMIT 5")
print(data)
