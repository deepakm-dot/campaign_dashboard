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

# Method A: Net Revenue (matching POS total Rs 5,298,958.69)
# All rows in azure_sales_report for PAVR Aug 6-9
sql_net = """
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

        -- Mobile: actual handsets (im.product = 'MOBILE' or telecom mobile category, excluding spare parts)
        (im.product = 'MOBILE'
         OR (lower(im.item_category) IN ('mobile', 'mobiles', 'mobile smart phone', 'mobile feature phone', 'mobile gsm phone')
             AND coalesce(im.category, '') = 'TELECOM')), 'Mobile',

        -- Laptop: actual laptops (im.product = 'LAPTOP' or IT laptop, excluding bags/stands)
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
    count()                                       AS line_items,
    sum(toInt64(s.qty))                           AS qty_sold,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) AS net_revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR'
  AND toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
GROUP BY product_type
ORDER BY net_revenue DESC
"""

rows = ch_query(sql_net)
print("=== NET REVENUE CATEGORY BREAKDOWN (All 841 lines including returns & exchanges) ===")
tot_qty = 0
tot_rev = 0
for r in rows:
    tot_qty += int(r['qty_sold'])
    tot_rev += float(r['net_revenue'])
    print(f"  {r['product_type']:18s} | lines: {r['line_items']:4d} | qty: {int(r['qty_sold']):4d} | rev: Rs {float(r['net_revenue']):12,.2f}")

print("-" * 65)
print(f"  {'TOTAL':18s} | lines: {sum(int(r['line_items']) for r in rows):4d} | qty: {tot_qty:4d} | rev: Rs {tot_rev:12,.2f}")
