import sqlite3
import sys
sys.path.append('backend')
from backend.main import query_clickhouse

conn = sqlite3.connect('backend/campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=732')
mobiles = [r[0] for r in c.fetchall()]

chunk_size = 10000
all_customers = []

for i in range(0, len(mobiles), chunk_size):
    chunk = mobiles[i:i+chunk_size]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''SELECT customer_mobile
    FROM azure_invoice_report 
    WHERE customer_mobile IN ({m_str}) 
    AND date >= '2026-08-06' AND date <= '2026-08-09' 
    AND branch = 'VPF'
    GROUP BY customer_mobile'''
    
    data = query_clickhouse(q)
    all_customers.extend([d['customer_mobile'] for d in data])

sales_data = []
chunk_size_2 = 50
for i in range(0, len(all_customers), chunk_size_2):
    chunk = all_customers[i:i+chunk_size_2]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''SELECT s.customer_mobile, groupArray(im.product) as products, groupArray(im.category) as categories
    FROM azure_sales_report s
    LEFT JOIN item_master im ON s.item_code = im.item_code
    WHERE s.customer_mobile IN ({m_str})
    AND toDate(s.date) >= '2026-08-06' AND toDate(s.date) <= '2026-08-09'
    AND s.branch = 'VPF'
    GROUP BY s.customer_mobile'''
    
    data = query_clickhouse(q)
    sales_data.extend(data)

core_products = ['MOBILE', 'TV', 'LAPTOP', 'AIR CONDITIONER', 'REFRIGERATORS', 'WASHING MACHINES']

core_only = 0
acc_only = 0
mixed = 0

for row in sales_data:
    prods = row['products']
    has_core = any(p in core_products for p in prods)
    has_acc = any(p not in core_products for p in prods)
    
    if has_core and not has_acc:
        core_only += 1
    elif has_acc and not has_core:
        acc_only += 1
    elif has_core and has_acc:
        mixed += 1

print(f"Total with Core: {core_only + mixed}")
print(f"Bought Accessories only: {acc_only}")
