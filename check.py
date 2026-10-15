
import sqlite3
conn = sqlite3.connect('backend/data.db')
c = conn.cursor()
c.execute('SELECT * FROM campaigns WHERE campaign_name LIKE \'%Falnir%\'')
for row in c.fetchall():
    print(row)
c.execute('SELECT count(*) FROM campaign_customers WHERE campaign_id IN (SELECT id FROM campaigns WHERE campaign_name LIKE \'%Falnir%\')')
print('Customers:', c.fetchone()[0])

