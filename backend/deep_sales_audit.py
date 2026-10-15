import json, urllib.request, base64

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def ch_query(sql):
    req = urllib.request.Request(CH_URL)
    token = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', 'Basic ' + token)
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()).get('data', [])
    except Exception as e:
        print(f"Error: {e}")
        return []

print("=" * 80)
print("CHECK 1: azure_sales_report directly for branch='PAVR' Aug 6-9:")
r1 = ch_query("""
    SELECT count() as rows, 
           sum(qty) as total_qty, 
           sum(qty * sold_price) as total_sold_price,
           uniq(invoice_no) as unique_invoices
    FROM azure_sales_report
    WHERE branch = 'PAVR'
      AND toDate(date) >= '2026-08-06'
      AND toDate(date) <= '2026-08-09'
      AND sold_price > 0
""")
print("azure_sales_report direct:", r1)

print("=" * 80)
print("CHECK 2: azure_invoice_report directly for branch='PAVR' Aug 6-9:")
r2 = ch_query("""
    SELECT count() as rows,
           sum(invoice_total) as total_inv,
           uniq(invoice_no) as unique_invoices
    FROM azure_invoice_report
    WHERE branch = 'PAVR'
      AND toDate(date) >= '2026-08-06'
      AND toDate(date) <= '2026-08-09'
      AND invoice_total > 0
""")
print("azure_invoice_report direct:", r2)

print("=" * 80)
print("CHECK 3: Are any items in azure_sales_report NOT in item_master?")
r3 = ch_query("""
    SELECT count() as missing_in_item_master,
           sum(s.qty) as missing_qty,
           sum(s.qty * s.sold_price) as missing_rev
    FROM azure_sales_report s
    LEFT JOIN item_master im ON im.item_code = s.item_code
    WHERE s.branch = 'PAVR'
      AND toDate(s.date) >= '2026-08-06'
      AND toDate(s.date) <= '2026-08-09'
      AND s.sold_price > 0
      AND im.item_code = ''
""")
print("Missing in item_master:", r3)

print("=" * 80)
print("CHECK 4: Did invoice date vs sales date differ for any PAVR records?")
r4 = ch_query("""
    SELECT count() as date_diff_cnt
    FROM azure_sales_report s
    JOIN azure_invoice_report inv ON inv.invoice_no = s.invoice_no
    WHERE (s.branch = 'PAVR' OR inv.branch = 'PAVR')
      AND toDate(s.date) != toDate(inv.date)
""")
print("Date diff between sales and invoice:", r4)

print("=" * 80)
print("CHECK 5: All distinct categories / products in azure_sales_report for PAVR Aug 6-9:")
r5 = ch_query("""
    SELECT 
        im.category,
        im.item_category,
        count() as lines,
        sum(s.qty) as units,
        sum(s.qty * s.sold_price) as rev
    FROM azure_sales_report s
    LEFT JOIN item_master im ON im.item_code = s.item_code
    WHERE s.branch = 'PAVR'
      AND toDate(s.date) >= '2026-08-06'
      AND toDate(s.date) <= '2026-08-09'
      AND s.sold_price > 0
    GROUP BY im.category, im.item_category
    ORDER BY rev DESC
""")
print(f"Total category breakdown rows: {len(r5)}")
for x in r5[:30]:
    print(f"  cat={x.get('category',''):20s} | item_cat={x.get('item_category',''):30s} | units={x.get('units'):5.0f} | rev=₹{float(x.get('rev',0)):12,.2f}")
