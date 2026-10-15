from backend.main import query_clickhouse
res = query_clickhouse("""
SELECT im.product, sum(toInt64(qty)) as net_qty, sum(if(toFloat64(sold_price) > 0, toInt64(qty), 0)) as paid_qty, sum(toFloat64(sold_price) * toInt64(qty)) as revenue
FROM azure_sales_report s
JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'POLE' AND toDate(s.date) >= '2026-09-03' AND toDate(s.date) <= '2026-09-06'
GROUP BY im.product
ORDER BY revenue DESC
LIMIT 20
""")
for r in res:
    print(r)
