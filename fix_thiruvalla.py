import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("UPDATE campaigns SET branch_code='TVF' WHERE campaign_name='Thiruvalla Future'")
conn.commit()
conn.close()
