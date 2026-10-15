import sys
sys.path.append('backend')
import main
import sqlite3
import urllib.request, json

url = 'https://script.google.com/macros/s/AKfycbwLu3feQq0BCxUFFxpUhamKLfNa5njxmJLZ4yBRY9pmPtsgBIXEFSzeVADBt5hlG9Y_DQ/exec'
rows = json.loads(urllib.request.urlopen(url).read().decode())
row = next(r for r in rows if r['Campaign Name'] == 'Kanjirappally Future')
print('ROW:', row)
campaign_id = 31352
query_start = row.get('Start Date')[:10] if row.get('Start Date') else ''
query_end = row.get('End Date')[:10] if row.get('End Date') else ''
print('Dates:', query_start, query_end)

b_filter = "AND branch = 'KJF'"
query = (f"SELECT customer_mobile, groupArray(invoice_no) as invoices, SUM(invoice_total) as customer_total "
         f"FROM azure_invoice_report "
         f"WHERE date >= '{query_start}' AND date <= '{query_end} 23:59:59' {b_filter} "
         f"GROUP BY customer_mobile")
print('Q:', query)
store_data = main.query_clickhouse(query)
print('Store_data len:', len(store_data))

conn = main.get_db(); c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?', (campaign_id,))
mobiles = [r['customer_mobile'] for r in c.fetchall() if r['customer_mobile']]
print('Mobiles in DB:', len(mobiles))
mobile_set = set(mobiles)

all_invoice_nos = set()
for r in store_data:
    if r.get('customer_mobile') in mobile_set:
        for inv in (r.get('invoices') or []):
            all_invoice_nos.add(inv)
print('all_invoice_nos len:', len(all_invoice_nos))

if all_invoice_nos:
    invoice_list_str = ", ".join(f"'{inv}'" for inv in list(all_invoice_nos)[:5000])
    brand_query = (f"SELECT im.brand, SUM(s.sold_price * s.qty) as revenue, SUM(if(toFloat64(s.sold_price) < 0, -toInt64(s.qty), toInt64(s.qty))) as qty "
                   f"FROM azure_sales_report s "
                   f"JOIN item_master im ON s.item_code = im.item_code "
                   f"WHERE s.invoice_no IN ({invoice_list_str}) "
                   f"GROUP BY im.brand ORDER BY revenue DESC LIMIT 5")
    brand_data = main.query_clickhouse(brand_query)
    print('Brands:', brand_data)
