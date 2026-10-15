import sqlite3
import sys
sys.path.append('backend')
from backend.main import query_clickhouse

conn = sqlite3.connect('backend/campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=732')
mobiles = set(r[0] for r in c.fetchall())

q = f'''
SELECT s.customer_mobile, SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as val
FROM azure_sales_report s
INNER JOIN item_master im ON s.item_code = im.item_code
WHERE s.branch = 'VPF' AND toDate(s.date) >= '2026-08-06' AND toDate(s.date) <= '2026-08-09'
GROUP BY s.customer_mobile
'''

data = query_clickhouse(q)

matched_customers = 0
total_revenue = 0.0

for row in data:
    if row['customer_mobile'] in mobiles:
        matched_customers += 1
        total_revenue += float(row['val'])

print(f'Count: {matched_customers}, Revenue: {total_revenue}')
