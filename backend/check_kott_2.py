import sqlite3
import re
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT id, campaign_name, branch_code FROM campaigns WHERE campaign_name LIKE '%Kottakkal%'")
print([dict(r) for r in c.fetchall()])
conn.close()
