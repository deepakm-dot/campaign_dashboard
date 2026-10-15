import sqlite3
import sys
sys.path.append('backend')
from backend.main import query_clickhouse

conn = sqlite3.connect('backend/campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=794')
mobiles = [r['customer_mobile'] for r in c.fetchall()]

chunk_size = 10000

# 1. No branch filter, 3 days
total_val_1 = 0
customers_1 = set()
for i in range(0, len(mobiles), chunk_size):
    chunk = mobiles[i:i+chunk_size]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''SELECT customer_mobile, SUM(invoice_total) as val 
    FROM azure_invoice_report 
    WHERE customer_mobile IN ({m_str}) 
    AND date >= '2026-09-03' AND date <= '2026-09-05' 
    GROUP BY customer_mobile'''
    data = query_clickhouse(q)
    for r in data:
        customers_1.add(r['customer_mobile'])
        total_val_1 += float(r.get('val', 0))
print(f"No branch, 3 days (Sept 3-5): {len(customers_1)} / {total_val_1}")

# 2. No branch filter, 4 days
total_val_2 = 0
customers_2 = set()
for i in range(0, len(mobiles), chunk_size):
    chunk = mobiles[i:i+chunk_size]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''SELECT customer_mobile, SUM(invoice_total) as val 
    FROM azure_invoice_report 
    WHERE customer_mobile IN ({m_str}) 
    AND date >= '2026-09-03' AND date <= '2026-09-06' 
    GROUP BY customer_mobile'''
    data = query_clickhouse(q)
    for r in data:
        customers_2.add(r['customer_mobile'])
        total_val_2 += float(r.get('val', 0))
print(f"No branch, 4 days (Sept 3-6): {len(customers_2)} / {total_val_2}")

# 3. Branch filter, 3 days
total_val_3 = 0
customers_3 = set()
for i in range(0, len(mobiles), chunk_size):
    chunk = mobiles[i:i+chunk_size]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''SELECT customer_mobile, SUM(invoice_total) as val 
    FROM azure_invoice_report 
    WHERE customer_mobile IN ({m_str}) 
    AND date >= '2026-09-03' AND date <= '2026-09-05' 
    AND branch = 'KLF'
    GROUP BY customer_mobile'''
    data = query_clickhouse(q)
    for r in data:
        customers_3.add(r['customer_mobile'])
        total_val_3 += float(r.get('val', 0))
print(f"Branch KLF, 3 days (Sept 3-5): {len(customers_3)} / {total_val_3}")

# 4. Branch filter, 4 days
total_val_4 = 0
customers_4 = set()
for i in range(0, len(mobiles), chunk_size):
    chunk = mobiles[i:i+chunk_size]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''SELECT customer_mobile, SUM(invoice_total) as val 
    FROM azure_invoice_report 
    WHERE customer_mobile IN ({m_str}) 
    AND date >= '2026-09-03' AND date <= '2026-09-06' 
    AND branch = 'KLF'
    GROUP BY customer_mobile'''
    data = query_clickhouse(q)
    for r in data:
        customers_4.add(r['customer_mobile'])
        total_val_4 += float(r.get('val', 0))
print(f"Branch KLF, 4 days (Sept 3-6): {len(customers_4)} / {total_val_4}")
