import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("SELECT id FROM campaigns WHERE campaign_name LIKE '%Kottakkal Future%'")
print('ID:', c.fetchone()[0])
conn.close()
