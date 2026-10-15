from check_missing import ch_query

print("=== Dates of AC, WM, Ref sold in PAVR in August 2026 ===")
r = ch_query("""
    SELECT 
        toDate(s.date) as dt,
        im.item_category,
        count() as cnt,
        sum(s.qty) as units,
        sum(s.qty * s.sold_price) as rev
    FROM azure_sales_report s
    JOIN item_master im ON im.item_code = s.item_code
    WHERE s.branch = 'PAVR'
      AND toDate(s.date) >= '2026-08-01'
      AND toDate(s.date) <= '2026-08-31'
      AND (
           lower(im.item_category) LIKE '%ac%'
        OR lower(im.item_category) LIKE '%wash%'
        OR lower(im.item_category) LIKE '%wm%'
        OR lower(im.item_category) LIKE '%ref%'
      )
      AND s.sold_price > 0
    GROUP BY dt, im.item_category
    ORDER BY dt ASC
""")
for x in r:
    print(x)
