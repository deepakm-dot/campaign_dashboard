from check_missing import ch_query

print("=== All categories in PAVR for the entire month of August 2026 ===")
r = ch_query("""
    SELECT 
        im.category,
        im.item_category,
        count() as lines,
        sum(s.qty) as units,
        sum(s.qty * s.sold_price) as rev
    FROM azure_sales_report s
    LEFT JOIN item_master im ON im.item_code = s.item_code
    WHERE s.branch = 'PAVR'
      AND toDate(s.date) >= '2026-08-01'
      AND toDate(s.date) <= '2026-08-31'
      AND s.sold_price > 0
      AND (
           lower(im.item_category) LIKE '%ac%'
        OR lower(im.item_category) LIKE '%air%'
        OR lower(im.item_category) LIKE '%wash%'
        OR lower(im.item_category) LIKE '%wm%'
        OR lower(im.item_category) LIKE '%ref%'
        OR lower(im.item_category) LIKE '%fridge%'
        OR lower(im.item_name) LIKE '%ac%'
        OR lower(im.item_name) LIKE '%refrigerator%'
        OR lower(im.item_name) LIKE '%washing%'
      )
    GROUP BY im.category, im.item_category
    ORDER BY rev DESC
""")
for x in r:
    print(x)
