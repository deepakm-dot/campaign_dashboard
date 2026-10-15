import sqlite3
import sys
sys.path.append('backend')
from backend.main import query_clickhouse
conn = sqlite3.connect('backend/campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

def test_camp(cid, b, start, d3, d4):
    c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?', (cid,))
    mobiles = [r['customer_mobile'] for r in c.fetchall()]
    chunk_size = 10000
    for title, no_branch, end_date in [('No branch, 3 days', True, d3), ('No branch, 4 days', True, d4), ('Branch, 3 days', False, d3), ('Branch, 4 days', False, d4)]:
        tot_val = 0
        cust = set()
        for i in range(0, len(mobiles), chunk_size):
            chunk = mobiles[i:i+chunk_size]
            m_str_chunk = ', '.join(f"'{m}'" for m in chunk)
            q = f'''SELECT customer_mobile, SUM(invoice_total) as val FROM azure_invoice_report 
            WHERE customer_mobile IN ({m_str_chunk}) AND date >= '{start}' AND date <= '{end_date}' '''
            if not no_branch: q += f''' AND branch = '{b}' '''
            q += ' GROUP BY customer_mobile'
            data = query_clickhouse(q)
            for r in data:
                cust.add(r['customer_mobile'])
                tot_val += float(r.get('val', 0))
        print(f'{cid} - {title}: {len(cust)} / {tot_val}')

test_camp(731, 'PAVR', '2026-08-06', '2026-08-08', '2026-08-09')
test_camp(732, 'VPF', '2026-08-06', '2026-08-08', '2026-08-09')
