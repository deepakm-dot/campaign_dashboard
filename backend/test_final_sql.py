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

# In the POS Daily Sales Report:
# Total Net Amount = 5,298,958.69
# Total Quantity   = 826
# (814 regular sales + 13 exchange items - 1 return item = 826)

sql_final = """
SELECT
    multiIf(
        -- TV
        im.product = 'TV' 
        OR (lower(im.item_category) IN ('tv', 'tv 18 %', 'tv 28 %', 'signage tv')
            OR (lower(im.item_category) LIKE '%tv%' AND lower(im.item_category) NOT LIKE '%stick%' AND lower(im.item_category) NOT LIKE '%stand%' AND lower(im.item_category) NOT LIKE '%frame%' AND lower(im.item_category) NOT LIKE '%access%')
            OR lower(im.item_category) LIKE '%television%'), 'TV',

        -- Washing machine
        im.product = 'WASHING MACHINES'
        OR (lower(im.item_category) LIKE '%washing machine%'
            OR lower(im.item_category) = 'wm'
            OR lower(im.item_category) LIKE 'wm %'
            OR lower(im.item_category) LIKE '% washer%'
            OR lower(im.item_category) = 'washer'
            OR lower(im.item_category) LIKE '%washer dryer%')
            AND lower(im.item_category) NOT LIKE '%cover%'
            AND lower(im.item_category) NOT LIKE '%dish%'
            AND lower(im.item_category) NOT LIKE '%pressure%', 'Washing machine',

        -- Refrigerator
        im.product = 'REFRIGERATORS'
        OR (lower(im.item_category) LIKE '%refrigerator%'
            OR lower(im.item_category) LIKE '%fridge%'
            OR lower(im.item_category) = 'ref'
            OR lower(im.item_category) LIKE 'ref %'
            OR lower(im.item_category) LIKE '% ref')
            AND lower(im.item_category) NOT LIKE '%stand%', 'Referigerator',

        -- Mobile: real mobile handsets
        (im.product = 'MOBILE'
         OR (lower(im.item_category) IN ('mobile', 'mobiles', 'mobile smart phone', 'mobile feature phone', 'mobile gsm phone')
             AND coalesce(im.category, '') = 'TELECOM')), 'Mobile',

        -- Laptop: real laptops
        (im.product = 'LAPTOP'
         OR (lower(im.item_category) = 'laptop'
             OR (lower(im.item_category) LIKE '%laptop%' AND lower(im.item_category) NOT LIKE '%bag%' AND lower(im.item_category) NOT LIKE '%acc%')
             OR lower(im.item_category) = 'notebook')), 'Laptop',

        -- AC
        im.product IN ('AIR CONDITIONER', 'AC OUTDOOR')
        OR (lower(im.item_category) IN ('ac', 'ac indoor', 'ac outdoor', 'air conditioner', 'inverter ac', 'tower ac')
            OR lower(im.item_category) LIKE '%air condition%'
            OR lower(im.item_category) LIKE '%ac indoor%'
            OR lower(im.item_category) LIKE '%ac outdoor%')
            AND lower(im.item_category) NOT LIKE '%access%'
            AND lower(im.item_category) NOT LIKE '%bracket%'
            AND lower(im.item_category) NOT LIKE '%dummy%', 'AC',

        'Other'
    ) AS product_type,
    sum(toInt64(s.qty))                           AS net_qty,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) AS net_revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR'
  AND toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
  AND (s.invoice_no NOT LIKE '%-EI-%')
GROUP BY product_type
ORDER BY net_revenue DESC
"""
rows = ch_query(sql_final)
print("Excluding internal EI (exchange disposal) invoices:")
tot_qty = 0
tot_rev = 0
for r in rows:
    tot_qty += int(r['net_qty'])
    tot_rev += float(r['net_revenue'])
    print(f"  {r['product_type']:18s} | qty: {int(r['net_qty']):4d} | rev: Rs {float(r['net_revenue']):12,.2f}")
print(f"  TOTAL: qty={tot_qty}, rev=Rs {tot_rev:,.2f}")
