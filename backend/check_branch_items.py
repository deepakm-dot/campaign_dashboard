"""
1. Find Paravoor and Vypin branch codes from azure_invoice_report
2. Check what item names/categories actually exist for those dates
3. Find what brands/items were sold - since categories are broad, we need item_name or brand
"""
import json, urllib.request, base64

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def ch_query(sql):
    req = urllib.request.Request(CH_URL)
    auth = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', 'Basic ' + auth)
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        res = urllib.request.urlopen(req)
        return json.loads(res.read()).get('data', [])
    except Exception as e:
        print(f"[CH ERROR] {e}")
        return []

# --- Test PAVR branch for Aug 6-9 ---
print("=" * 60)
print("PAVR branch Aug 6-9:")
rows = ch_query("""
    SELECT COUNT(DISTINCT customer_mobile) as cust,
           COUNT(DISTINCT invoice_no) as inv,
           SUM(invoice_total) as rev
    FROM azure_invoice_report
    WHERE branch='PAVR'
      AND toDate(date) >= '2026-08-06'
      AND toDate(date) <= '2026-08-09'
""")
for r in rows:
    print(f"  cust={r.get('cust')}  inv={r.get('inv')}  rev=₹{float(r.get('rev',0)):,.0f}")

# --- Find Vypin branch ---
print("\nBranches with 'V' that have Aug 6-9 data:")
rows2 = ch_query("""
    SELECT branch, COUNT(DISTINCT invoice_no) as inv, SUM(invoice_total) as rev
    FROM azure_invoice_report
    WHERE toDate(date) >= '2026-08-06' AND toDate(date) <= '2026-08-09'
      AND (branch LIKE 'V%' OR branch LIKE 'KY%')
    GROUP BY branch ORDER BY rev DESC
""")
for r in rows2:
    print(f"  branch={r.get('branch')}  inv={r.get('inv')}  rev=₹{float(r.get('rev',0)):,.0f}")

# --- Check item_master fields available ---
print("\n" + "=" * 60)
print("item_master columns (sample 5 rows):")
rows3 = ch_query("SELECT * FROM item_master LIMIT 5")
if rows3:
    print(f"  Columns: {list(rows3[0].keys())}")
    for r in rows3:
        print(f"  {r}")

# --- Check azure_sales_report sample ---
print("\n" + "=" * 60)
print("azure_sales_report sample (PAVR Aug 6-9, join item_master):")
rows4 = ch_query("""
    SELECT im.category, im.item_name, s.sold_price, s.qty
    FROM azure_invoice_report inv
    JOIN azure_sales_report s ON s.invoice_no = inv.invoice_no
    JOIN item_master im ON im.item_code = s.item_code
    WHERE inv.branch = 'PAVR'
      AND toDate(inv.date) >= '2026-08-06'
      AND toDate(inv.date) <= '2026-08-09'
    LIMIT 20
""")
for r in rows4:
    print(f"  cat={r.get('category','?'):25s}  item={r.get('item_name','?')[:40]:40s}  price={r.get('sold_price')}  qty={r.get('qty')}")

# --- Get distinct item_names to understand product naming ---
print("\n" + "=" * 60)
print("DISTINCT item categories with examples (PAVR Aug 6-9):")
rows5 = ch_query("""
    SELECT im.category,
           groupArray(im.item_name)[1] as example_item,
           COUNT() as cnt,
           SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as rev
    FROM azure_invoice_report inv
    JOIN azure_sales_report s ON s.invoice_no = inv.invoice_no
    JOIN item_master im ON im.item_code = s.item_code
    WHERE inv.branch = 'PAVR'
      AND toDate(inv.date) >= '2026-08-06'
      AND toDate(inv.date) <= '2026-08-09'
    GROUP BY im.category
    ORDER BY rev DESC
""")
for r in rows5:
    print(f"  cat={r.get('category','?'):30s}  example={r.get('example_item','?')[:35]:35s}  cnt={r.get('cnt')}  rev=₹{float(r.get('rev',0)):,.0f}")
