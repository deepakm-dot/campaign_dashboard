import sys
sys.path.append('backend')
from backend.main import query_clickhouse

d_filter = "toDate(i.date) >= '2026-08-06' AND toDate(i.date) <= '2026-08-09'"
b_filter = "AND i.branch = 'VPF'"
query = (f"SELECT i.customer_mobile as customer_mobile, "
         f"groupArray(s.invoice_no) as invoices, "
         f"SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as customer_total "
         f"FROM azure_invoice_report i "
         f"INNER JOIN azure_sales_report s ON i.invoice_no = s.invoice_no "
         f"LEFT JOIN item_master im ON s.item_code = im.item_code "
         f"WHERE {d_filter} {b_filter} "
         f"AND (im.category IS NULL OR im.category NOT IN ('ACCESSORIES', 'MOBILE ACCESSORIES', 'SERVICES', 'EXTENDED WARRANTY', 'DUMMY', 'ENDPOINT PROTECTION', 'VALUE ADDED SERVICE', 'OTHERS', 'TELECOM')) "
         f"GROUP BY i.customer_mobile")

try:
    print(query_clickhouse(query)[:2])
except Exception as e:
    print(e)
