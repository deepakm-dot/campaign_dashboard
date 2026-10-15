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

sql = """
SELECT
    multiIf(
        -- TV
        (lower(im.item_category) IN ('tv', 'tv 18 %', 'tv 28 %', 'signage tv')
         OR (lower(im.item_category) LIKE '%tv%' AND lower(im.item_category) NOT LIKE '%stick%' AND lower(im.item_category) NOT LIKE '%stand%' AND lower(im.item_category) NOT LIKE '%frame%' AND lower(im.item_category) NOT LIKE '%access%')
         OR lower(im.item_category) LIKE '%television%'), 'TV',

        -- Washing Machine
        (lower(im.item_category) LIKE '%washing machine%'
         OR lower(im.item_category) = 'wm'
         OR lower(im.item_category) LIKE 'wm %'
         OR lower(im.item_category) LIKE '% washer%'
         OR lower(im.item_category) = 'washer'
         OR lower(im.item_category) LIKE '%washer dryer%')
         AND lower(im.item_category) NOT LIKE '%cover%'
         AND lower(im.item_category) NOT LIKE '%dish%'
         AND lower(im.item_category) NOT LIKE '%pressure%', 'Washing machine',

        -- Refrigerator
        (lower(im.item_category) LIKE '%refrigerator%'
         OR lower(im.item_category) LIKE '%fridge%'
         OR lower(im.item_category) = 'ref'
         OR lower(im.item_category) LIKE 'ref %'
         OR lower(im.item_category) LIKE '% ref')
         AND lower(im.item_category) NOT LIKE '%stand%', 'Referigerator',

        -- Mobile
        (lower(im.item_category) IN ('mobile', 'mobiles', 'mobile smart phone', 'mobile feature phone', 'mobile gsm phone')
         OR (lower(im.item_category) LIKE '%mobile%' AND lower(im.item_category) NOT LIKE '%acc%' AND lower(im.item_category) NOT LIKE '%cover%' AND lower(im.item_category) NOT LIKE '%holder%' AND lower(im.item_category) NOT LIKE '%stand%' AND lower(im.item_category) NOT LIKE '%antivirus%' AND lower(im.item_category) NOT LIKE '%computer%' AND lower(im.item_category) NOT LIKE '%demo%')), 'Mobile',

        -- Laptop
        (lower(im.item_category) = 'laptop'
         OR (lower(im.item_category) LIKE '%laptop%' AND lower(im.item_category) NOT LIKE '%bag%' AND lower(im.item_category) NOT LIKE '%acc%')
         OR lower(im.item_category) = 'notebook'), 'Laptop',

        -- AC
        (lower(im.item_category) IN ('ac', 'ac indoor', 'ac outdoor', 'air conditioner', 'inverter ac', 'tower ac')
         OR lower(im.item_category) LIKE '%air condition%'
         OR lower(im.item_category) LIKE '%ac indoor%'
         OR lower(im.item_category) LIKE '%ac outdoor%')
         AND lower(im.item_category) NOT LIKE '%access%'
         AND lower(im.item_category) NOT LIKE '%bracket%'
         AND lower(im.item_category) NOT LIKE '%dummy%', 'AC',

        'Other'
    ) AS product_type,
    SUM(toInt64(s.qty))                            AS qty_sold,
    SUM(toFloat64(s.sold_price) * toInt64(s.qty))  AS revenue,
    COUNT()                                        AS line_items
FROM azure_invoice_report inv
JOIN azure_sales_report s  ON s.invoice_no = inv.invoice_no
JOIN item_master        im ON im.item_code  = s.item_code
WHERE toDate(inv.date) >= '2026-08-06'
  AND toDate(inv.date) <= '2026-08-09'
  AND inv.branch        = 'PAVR'
  AND toFloat64(s.sold_price) > 0
GROUP BY product_type
ORDER BY revenue DESC
"""

rows = ch_query(sql)
print(f"Results for PAVR (2026-08-06 to 2026-08-09):")
total_qty = 0
total_rev = 0
for r in rows:
    qty = int(r['qty_sold'])
    rev = float(r['revenue'])
    total_qty += qty
    total_rev += rev
    print(f"  {r['product_type']:18s} : qty = {qty:4d}, rev = ₹{rev:12,.2f} ({r['line_items']} lines)")

print(f"  {'TOTAL':18s} : qty = {total_qty:4d}, rev = ₹{total_rev:12,.2f}")
