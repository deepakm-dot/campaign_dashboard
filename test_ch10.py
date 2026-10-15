import sys
sys.path.append('backend')
import main
import sqlite3

conn = main.get_db()
c = conn.cursor()
c.execute('SELECT start_date, end_date FROM campaigns WHERE campaign_name="Palakkad Future"')
sd, ed = c.fetchone()

q = f"""SELECT customer_mobile, SUM(invoice_total) as customer_total 
FROM azure_invoice_report 
WHERE date >= '{sd[:10]}' AND date <= '{ed[:10]} 23:59:59' AND branch = 'PKD' 
GROUP BY customer_mobile"""
data = main.query_clickhouse(q)

c.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31338")
mobiles = set(r[0] for r in c.fetchall() if r[0])

purchased = 0
for r in data:
    if r.get('customer_mobile') in mobiles:
        purchased += 1

print(f"Total purchased: {purchased}")
