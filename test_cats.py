import sqlite3
import sys
sys.path.append('backend')
from backend.main import query_clickhouse

conn = sqlite3.connect('backend/campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=732')
mobiles = [r[0] for r in c.fetchall()]

chunk_size = 500
all_categories = set()

for i in range(0, len(mobiles), chunk_size):
    chunk = mobiles[i:i+chunk_size]
    m_str = ', '.join(f"'{m}'" for m in chunk)
    q = f'''
    SELECT groupArray(im.category) as cats
    FROM azure_invoice_report i
    INNER JOIN azure_sales_report s ON i.invoice_no = s.invoice_no
    INNER JOIN item_master im ON s.item_code = im.item_code
    WHERE i.customer_mobile IN ({m_str}) 
    AND toDate(i.date) >= '2026-08-06' AND toDate(i.date) <= '2026-08-09' 
    AND i.branch = 'VPF'
    '''
    try:
        data = query_clickhouse(q)
        for d in data:
            for cat in d.get('cats', []):
                all_categories.add(cat)
    except:
        pass

print("Categories bought by campaign customers:")
print(all_categories)
