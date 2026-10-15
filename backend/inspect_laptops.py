from check_missing import ch_query

r = ch_query("""
SELECT im.item_code, im.item_name, im.category, im.item_category, s.qty, s.sold_price, (s.qty * s.sold_price) as rev
FROM azure_sales_report s
JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR'
  AND toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
  AND s.sold_price > 0
  AND (lower(im.item_category) LIKE '%laptop%' OR lower(im.item_name) LIKE '%laptop%')
""")
print(f"Total Laptop matching items: {len(r)}")
for x in r:
    cat = x.get('item_category') or ''
    name = x.get('item_name') or ''
    qty = x.get('qty') or 0
    rev = x.get('rev') or 0
    print(f"  {cat:20s} | {name:55s} | qty={qty} | rev={rev}")
