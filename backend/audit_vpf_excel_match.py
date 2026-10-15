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
    res = urllib.request.urlopen(req)
    return json.loads(res.read()).get('data', [])

# 1. Check AC in VPF
sql_ac = """
SELECT 
    s.item_code,
    im.product,
    im.item_category,
    im.category,
    im.item_name,
    toInt64(s.qty) as qty,
    toFloat64(s.sold_price) as price,
    s.invoice_no,
    s.date
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' 
  AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND (
      im.product IN ('AIR CONDITIONER', 'AC OUTDOOR')
      OR lower(im.item_category) LIKE '%ac%'
      OR lower(im.item_category) LIKE '%air condition%'
  )
ORDER BY s.date, s.invoice_no
"""
print("=== AC ROWS in VPF ===")
ac_data = ch_query(sql_ac)
indoor_qty = 0
outdoor_qty = 0
for r in ac_data:
    print(f"{r['date']} | {r['invoice_no']} | prod:{r['product']} | icat:{r['item_category']} | name:{r['item_name']} | qty:{r['qty']} | price:{r['price']}")
    if 'outdoor' in str(r['product']).lower() or 'outdoor' in str(r['item_category']).lower():
        outdoor_qty += r['qty']
    else:
        indoor_qty += r['qty']
print(f"Total AC rows: {len(ac_data)}, indoor_qty: {indoor_qty}, outdoor_qty: {outdoor_qty}")

# 2. Check TV in VPF
sql_tv = """
SELECT 
    s.item_code,
    im.product,
    im.item_category,
    im.category,
    im.item_name,
    toInt64(s.qty) as qty,
    toFloat64(s.sold_price) as price,
    s.invoice_no,
    s.date
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' 
  AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND (
      im.product = 'TV'
      OR lower(im.item_category) LIKE '%tv%'
      OR lower(im.item_category) LIKE '%television%'
  )
ORDER BY s.date, s.invoice_no
"""
print("\n=== TV ROWS in VPF ===")
tv_data = ch_query(sql_tv)
paid_tv = 0
zero_tv = 0
neg_tv = 0
for r in tv_data:
    p = r['price']
    q = r['qty']
    if p > 0:
        paid_tv += q
    elif p == 0:
        zero_tv += q
    else:
        neg_tv += q
    print(f"{r['date']} | {r['invoice_no']} | prod:{r['product']} | icat:{r['item_category']} | name:{r['item_name']} | qty:{q} | price:{p}")
print(f"Total TV rows: {len(tv_data)}, paid_tv: {paid_tv}, zero_tv: {zero_tv}, neg_tv: {neg_tv}, net: {paid_tv + zero_tv + neg_tv}")

# 3. Check WASHING MACHINES in VPF
sql_wm = """
SELECT 
    s.item_code,
    im.product,
    im.item_category,
    im.category,
    im.item_name,
    toInt64(s.qty) as qty,
    toFloat64(s.sold_price) as price,
    s.invoice_no,
    s.date
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' 
  AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND (
      im.product = 'WASHING MACHINES'
      OR lower(im.item_category) LIKE '%washing machine%'
      OR lower(im.item_category) = 'wm'
      OR lower(im.item_category) LIKE 'wm %'
      OR lower(im.item_category) LIKE '%washer%'
  )
ORDER BY s.date, s.invoice_no
"""
print("\n=== WASHING MACHINES in VPF ===")
wm_data = ch_query(sql_wm)
paid_wm = 0
for r in wm_data:
    print(f"{r['date']} | {r['invoice_no']} | prod:{r['product']} | icat:{r['item_category']} | name:{r['item_name']} | qty:{r['qty']} | price:{r['price']}")
    paid_wm += r['qty']
print(f"Total WM rows: {len(wm_data)}, total qty: {paid_wm}")

# 4. Check MOBILE in VPF
sql_mob = """
SELECT 
    s.item_code,
    im.product,
    im.item_category,
    im.category,
    im.item_name,
    toInt64(s.qty) as qty,
    toFloat64(s.sold_price) as price,
    s.invoice_no,
    s.date
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' 
  AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND (
      im.product = 'MOBILE'
      OR lower(im.item_category) LIKE '%mobile%'
      OR lower(im.item_category) LIKE '%phone%'
  )
ORDER BY s.date, s.invoice_no
"""
print("\n=== MOBILE in VPF ===")
mob_data = ch_query(sql_mob)
paid_mob = 0
for r in mob_data:
    if r['price'] > 0:
        paid_mob += r['qty']
print(f"Total Mobile rows: {len(mob_data)}, paid_mob: {paid_mob}")
# Group mobile by product & item_category
mob_cat_map = {}
for r in mob_data:
    k = (r['product'], r['item_category'], r['category'], r['price'] > 0)
    mob_cat_map[k] = mob_cat_map.get(k, 0) + r['qty']
for k, v in sorted(mob_cat_map.items()):
    print(f"Mobile group: prod={k[0]}, icat={k[1]}, cat={k[2]}, paid={k[3]} => qty={v}")
