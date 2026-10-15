from check_missing import ch_query

r = ch_query("""
SELECT im.item_code, im.item_name, im.category, im.item_category, count() as cnt, sum(s.qty) as qty, sum(s.qty * s.sold_price) as rev
FROM azure_sales_report s
JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR'
  AND toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
  AND s.sold_price > 0
  AND im.item_category IN ('MOBILE SMART PHONE', 'MOBILE FEATURE PHONE')
GROUP BY im.item_code, im.item_name, im.category, im.item_category
ORDER BY rev ASC
""")
print(f"Total distinct items in Mobile: {len(r)}")
for x in r[:20]:
    print(f"  cat={x['category']:10s} | {x['item_name']:50s} | qty={x['qty']} | rev={x['rev']}")
