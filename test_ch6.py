import sys
sys.path.append('backend')
import main
import sqlite3

c = sqlite3.connect('campaign_dashboard.db').cursor()
c.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31352")
mobiles = set(r[0] for r in c.fetchall() if r[0])
print("Mobiles length:", len(mobiles))

q = """SELECT customer_mobile, groupArray(invoice_no) as invoices, SUM(invoice_total) as customer_total 
FROM azure_invoice_report 
WHERE toDate(date) >= '2026-09-03' AND toDate(date) <= '2026-09-06' AND branch = 'KJF' 
GROUP BY customer_mobile"""
data = main.query_clickhouse(q)

matched = []
invoices = set()
for r in data:
    if r.get('customer_mobile') in mobiles:
        matched.append(r)
        for i in r.get('invoices', []): invoices.add(i)

print("Matched customers:", len(matched))
print("Matched invoices:", len(invoices))
if invoices:
    q2 = f"""SELECT im.brand, SUM(s.sold_price * s.qty) as revenue, SUM(s.qty) as qty 
             FROM azure_sales_report s JOIN item_master im ON s.item_code = im.item_code 
             WHERE s.invoice_no IN ({", ".join(f"'{i}'" for i in list(invoices)[:5000])}) 
             GROUP BY im.brand ORDER BY revenue DESC LIMIT 5"""
    print(main.query_clickhouse(q2))
