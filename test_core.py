import sqlite3
import sys
sys.path.append('backend')
from backend.main import query_clickhouse

conn = sqlite3.connect('backend/campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=732')
mobiles = [r[0] for r in c.fetchall()]

chunk_size = 1000
all_customers = set()
total_rev = 0.0

for i in range(0, len(mobiles), chunk_size):
    chunk = mobiles[i:i+chunk_size]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''
    SELECT s.customer_mobile, SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as val
    FROM azure_sales_report s
    INNER JOIN item_master im ON s.item_code = im.item_code
    WHERE s.customer_mobile IN ({m_str}) 
    AND toDate(s.date) >= '2026-08-06' AND toDate(s.date) <= '2026-08-09' 
    AND s.branch = 'VPF'
    -- Only include core items if necessary, let's start with just the INNER JOIN
    GROUP BY s.customer_mobile
    '''
    try:
        data = query_clickhouse(q)
        for d in data:
            all_customers.add(d['customer_mobile'])
            total_rev += float(d['val'])
    except Exception as e:
        print(e)

print(f'Count: {len(all_customers)}, Revenue: {total_rev}')
