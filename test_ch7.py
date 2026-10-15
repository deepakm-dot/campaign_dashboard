import sys
sys.path.append('backend')
import main
import sqlite3

c = main.get_db().cursor()
c.execute('SELECT start_date, end_date FROM campaigns WHERE id=31352')
sd, ed = c.fetchone()
q = f"""SELECT customer_mobile, groupArray(invoice_no) as invoices, SUM(invoice_total) as customer_total 
FROM azure_invoice_report 
WHERE date >= '{sd}' AND date <= '{ed}' AND branch = 'KJF' 
GROUP BY customer_mobile"""
print('Query:', q)
data = main.query_clickhouse(q)
print('Rows:', len(data))
