from backend.main import query_clickhouse
res = query_clickhouse("""
SELECT count(*)
FROM azure_sales_report s
JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'POLE' AND toDate(s.date) >= '2026-09-03' AND toDate(s.date) <= '2026-09-06'
AND im.product = 'TV' AND toFloat64(s.sold_price) = 0
""")
for r in res:
    print(r)
