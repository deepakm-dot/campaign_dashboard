import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("SELECT id, campaign_name FROM campaigns WHERE campaign_name LIKE '%Kottakkal%'")
camps = c.fetchall()
for camp in camps:
    print('Campaign:', camp)
    c.execute('SELECT COUNT(*) FROM campaign_customers WHERE campaign_id=?', (camp[0],))
    print('Customers:', c.fetchone()[0])
conn.close()
