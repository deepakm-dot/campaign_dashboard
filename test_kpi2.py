import sqlite3
import sys
sys.path.append('backend')
from backend.main import query_clickhouse

conn = sqlite3.connect('backend/campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

def check(cid, b, sd, ed):
    c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?', (cid,))
    mobiles = [r['customer_mobile'] for r in c.fetchall()]
    m_str = ', '.join(f"'{m}'" for m in mobiles)
    
    q = f'''SELECT COUNT(DISTINCT customer_mobile) as c, SUM(invoice_total) as v 
    FROM azure_invoice_report 
    WHERE customer_mobile IN ({m_str}) 
    AND date >= '{sd}' AND date <= '{ed}' 
    AND branch = '{b}' '''
    
    chunk_size = 10000
    total_val = 0
    customers = set()

    for i in range(0, len(mobiles), chunk_size):
        chunk = mobiles[i:i+chunk_size]
        m_str_chunk = ', '.join(f"'{m}'" for m in chunk)
        q = f'''SELECT customer_mobile, SUM(invoice_total) as val 
        FROM azure_invoice_report 
        WHERE customer_mobile IN ({m_str_chunk}) 
        AND date >= '{sd}' AND date <= '{ed}' 
        AND branch = '{b}' 
        GROUP BY customer_mobile'''
        data = query_clickhouse(q)
        for r in data:
            customers.add(r['customer_mobile'])
            total_val += float(r.get('val', 0))

    print(f"Campaign {cid}: Purchases: {len(customers)}, Revenue: {total_val}")

check(731, 'PAVR', '2026-08-06', '2026-08-08')
check(732, 'VPF', '2026-08-06', '2026-08-08')
