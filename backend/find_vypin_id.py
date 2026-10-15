import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT id, campaign_name, type, start_date, end_date FROM campaigns WHERE lower(campaign_name) LIKE '%vypin%'")
for r in c.fetchall():
    print(dict(r))
conn.close()
