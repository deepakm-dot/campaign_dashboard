import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("UPDATE campaigns SET branch_code='KTF' WHERE campaign_name LIKE '%Kottakkal Future%'")
conn.commit()
print('Updated', c.rowcount, 'rows')
conn.close()
