import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("UPDATE campaigns SET purchase_value=0, roi=0 WHERE campaign_name='Thiruvalla Future'")
conn.commit()
conn.close()
