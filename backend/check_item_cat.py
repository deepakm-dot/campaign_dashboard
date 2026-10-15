"""
1. Find Vypin branch by checking item_category values for product classification
2. Check item_category vs item_name for TV/AC/WM/Ref/Mobile/Laptop detection
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

# Find distinct item_category in item_master (this is the granular field)
print("=" * 60)
print("DISTINCT item_category values in item_master:")
print("=" * 60)
rows = ch_query("""
    SELECT DISTINCT item_category, category, COUNT() as cnt
    FROM item_master
    GROUP BY item_category, category
    ORDER BY cnt DESC
    LIMIT 80
""")
for r in rows:
    print(f"  item_cat={r.get('item_category',''):35s}  cat={r.get('category',''):20s}  cnt={r.get('cnt')}")

# Check PAVR item_category breakdown for Aug 6-9
print("\n" + "=" * 60)
print("PAVR item_category breakdown Aug 6-9:")
print("=" * 60)
rows2 = ch_query("""
    SELECT im.item_category,
           im.category,
           COUNT() as line_items,
           SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as rev
    FROM azure_invoice_report inv
    JOIN azure_sales_report s ON s.invoice_no = inv.invoice_no
    JOIN item_master im ON im.item_code = s.item_code
    WHERE inv.branch = 'PAVR'
      AND toDate(inv.date) >= '2026-08-06'
      AND toDate(inv.date) <= '2026-08-09'
      AND toFloat64(s.sold_price) > 0
    GROUP BY im.item_category, im.category
    ORDER BY rev DESC
""")
for r in rows2:
    print(f"  item_cat={r.get('item_category','?'):35s}  cat={r.get('category','?'):20s}  lines={r.get('line_items')}  rev=₹{float(r.get('rev',0)):>12,.0f}")

# Find Vypin candidates - check Book1 style by looking at campaign name context
# Vypin is a place in Ernakulam district, Kerala
# VPF, VKY, VLC, VMF, VKY could be Vypin
# Let's check which branch had the most matching with Vypin Onam customer mobiles

import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=732 LIMIT 100")
vypin_mobiles = [r['customer_mobile'] for r in cur.fetchall()]
conn.close()

print("\n" + "=" * 60)
print("Which branch matches Vypin campaign customers best?")
print("=" * 60)
in_list = ",".join(f"'{m}'" for m in vypin_mobiles)
rows3 = ch_query(f"""
    SELECT branch,
           COUNT(DISTINCT customer_mobile) as cust,
           COUNT(DISTINCT invoice_no) as inv,
           SUM(invoice_total) as rev
    FROM azure_invoice_report
    WHERE customer_mobile IN ({in_list})
      AND toDate(date) >= '2026-08-06'
      AND toDate(date) <= '2026-08-08'
    GROUP BY branch
    ORDER BY cust DESC
    LIMIT 10
""")
for r in rows3:
    print(f"  branch={r.get('branch',''):6s}  cust={r.get('cust')}  inv={r.get('inv')}  rev=₹{float(r.get('rev',0)):,.0f}")
