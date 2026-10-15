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

# 1. Total rows, quantities, and amount for VPF Aug 6-9
sql_vpf = """
SELECT 
    count() as total_lines,
    sum(qty) as total_qty,
    sum(sold_price * qty) as net_amount,
    sumIf(sold_price * qty, sold_price > 0) as gross_amount,
    sumIf(sold_price * qty, sold_price < 0) as deductions
FROM azure_sales_report
WHERE branch = 'VPF' AND toDate(date) BETWEEN '2026-08-06' AND '2026-08-09'
"""
print("VPF Totals:")
print(ch_query(sql_vpf))

# 2. Check VPF daily breakdown in azure_sales_report
sql_vpf_daily = """
SELECT 
    toDate(date) as dt,
    count() as total_lines,
    countIf(sold_price > 0) as pos_lines,
    countIf(sold_price = 0) as zero_lines,
    countIf(sold_price < 0) as neg_lines,
    sum(qty) as total_qty,
    sum(sold_price * qty) as net_amount
FROM azure_sales_report
WHERE branch = 'VPF' AND toDate(date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY dt ORDER BY dt
"""
print("\nVPF Daily:")
for r in ch_query(sql_vpf_daily):
    print(r)

# 3. Product breakdown for VPF using our 7 categories
sql_vpf_prods = """
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
    count() as lines,
    sum(toInt64(s.qty)) as qty,
    sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF'
  AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY product_type
ORDER BY revenue DESC
"""
print("\nVPF Product Breakdown:")
for r in ch_query(sql_vpf_prods):
    print(f"  {r['product_type']:18s} | lines: {r['lines']:4d} | qty: {int(r['qty']):4d} | rev: Rs {float(r['revenue']):12,.2f}")
