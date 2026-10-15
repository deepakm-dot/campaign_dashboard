import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT * FROM campaigns WHERE id=31325")
print(dict(c.fetchone() or {}))
conn.close()
