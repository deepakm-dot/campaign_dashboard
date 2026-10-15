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
    q = f'''SELECT customer_mobile, SUM(invoice_total) as val 
    FROM azure_invoice_report 
    WHERE customer_mobile IN ({m_str}) 
    AND date >= '2026-08-06' AND date <= '2026-08-09' 
    AND branch = 'VPF'
    GROUP BY customer_mobile'''
    
    data = query_clickhouse(q)
    all_customers.extend(data)

positive = 0
negative = 0
zero = 0
for r in all_customers:
    val = float(r.get('val', 0))
    if val > 0: positive += 1
    elif val < 0: negative += 1
    else: zero += 1

print(f'Total: {len(all_customers)}, Positive: {positive}, Negative: {negative}, Zero: {zero}')
