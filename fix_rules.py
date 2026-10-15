import sqlite3
import sys
sys.path.append('backend')
from backend.main import calculate_kpis_for_campaign

conn = sqlite3.connect('backend/campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("UPDATE campaigns SET end_date='2026-08-09' WHERE id IN (731, 732)")
conn.commit()

c.execute('SELECT * FROM campaigns WHERE id=731')
camp = dict(c.fetchone())
calculate_kpis_for_campaign(c, 731, '2026-08-06', '2026-08-09', camp['budget'])

c.execute('SELECT * FROM campaigns WHERE id=732')
camp = dict(c.fetchone())
calculate_kpis_for_campaign(c, 732, '2026-08-06', '2026-08-09', camp['budget'])

conn.commit()
print("Recalculated with correct rules")
