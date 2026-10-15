from check_missing import ch_query

# Find all items that fell into 'Other'
sql = """
SELECT
    im.item_code,
    im.item_category,
    im.category,
    im.product,
    im.item_name,
    s.qty,
    s.sold_price,
    (s.qty * s.sold_price) as line_rev
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR'
  AND toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
  AND s.sold_price > 0
"""
rows = ch_query(sql)
print(f"Total sales rows: {len(rows)}")

# Let's inspect everything grouped by item_category
by_cat = {}
for r in rows:
    cat = str(r.get('item_category') or r.get('im.item_category') or '').strip()
    if cat not in by_cat:
        by_cat[cat] = {'qty': 0, 'rev': 0.0, 'sample': []}
    by_cat[cat]['qty'] += float(r.get('qty') or r.get('s.qty') or 0)
    by_cat[cat]['rev'] += float(r.get('line_rev') or 0)
    if len(by_cat[cat]['sample']) < 2:
        by_cat[cat]['sample'].append(r.get('item_name') or r.get('im.item_name'))

print("\nALL DISTINCT item_category in PAVR Aug 6-9:")
for c, d in sorted(by_cat.items(), key=lambda x: x[1]['rev'], reverse=True):
    print(f"  {c:30s} | qty={d['qty']:4.0f} | rev=₹{d['rev']:12,.2f} | sample={d['sample'][0] if d['sample'] else ''}")
