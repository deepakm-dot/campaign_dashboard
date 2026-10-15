import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
print(conn.cursor().execute("SELECT count(*) FROM campaign_customers WHERE campaign_id=31352").fetchone())
