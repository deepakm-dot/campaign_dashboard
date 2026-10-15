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

# Test the refined SQL for VPF:
# Rule for AC: Only take "ac indoor" (or im.product = 'AIR CONDITIONER').
# NEVER count "ac outdoor" for anything (exclude im.product = 'AC OUTDOOR' or lower(im.item_category) = 'ac outdoor' or lower(im.item_name) LIKE 'o/d%')

sql_vpf = """
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

        -- Referigerator
        im.product = 'REFRIGERATORS'
        OR (lower(im.item_category) LIKE '%refrigerator%'
            OR lower(im.item_category) LIKE '%fridge%'
            OR lower(im.item_category) = 'ref'
            OR lower(im.item_category) LIKE 'ref %'
            OR lower(im.item_category) LIKE '% ref')
            AND lower(im.item_category) NOT LIKE '%stand%', 'Referigerator',

        -- Mobile
        im.product = 'MOBILE'
        OR (lower(im.item_category) IN ('mobile', 'mobiles', 'mobile smart phone', 'mobile feature phone', 'mobile gsm phone')
            AND coalesce(im.category, '') = 'TELECOM'), 'Mobile',

        -- Laptop
        im.product = 'LAPTOP'
        OR (lower(im.item_category) = 'laptop'
            OR (lower(im.item_category) LIKE '%laptop%' AND lower(im.item_category) NOT LIKE '%bag%' AND lower(im.item_category) NOT LIKE '%acc%')
            OR lower(im.item_category) = 'notebook'), 'Laptop',

        -- AC: Take ONLY "ac indoor". NEVER count "ac outdoor" for anything.
        (im.product = 'AIR CONDITIONER'
         OR lower(im.item_category) IN ('ac indoor', 'air conditioner', 'inverter ac', 'tower ac')
         OR lower(im.item_category) LIKE '%ac indoor%'
         OR (lower(im.item_category) LIKE '%air condition%' AND lower(im.item_category) NOT LIKE '%outdoor%'))
         AND im.product != 'AC OUTDOOR'
         AND lower(im.item_category) NOT LIKE '%outdoor%'
         AND lower(im.item_name) NOT LIKE 'o/d%'
         AND lower(im.item_category) NOT LIKE '%access%'
         AND lower(im.item_category) NOT LIKE '%bracket%'
         AND lower(im.item_category) NOT LIKE '%dummy%', 'AC',

        'Other'
    ) AS product_type,
    count() as line_count,
    SUM(toInt64(s.qty)) AS total_qty,
    SUM(if(toFloat64(s.sold_price) > 0, toInt64(s.qty), 0)) AS paid_qty,
    SUM(toFloat64(s.sold_price) * toInt64(s.qty)) AS revenue
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
  AND s.branch = 'VPF'
  -- CRITICAL RULE: NEVER count 'ac outdoor' for anything
  AND im.product != 'AC OUTDOOR'
  AND lower(im.item_category) != 'ac outdoor'
  AND lower(im.item_name) NOT LIKE 'o/d%'
GROUP BY product_type
ORDER BY revenue DESC
"""

rows = ch_query(sql_vpf)
print("=== Refined SQL Results for VPF ===")
for r in rows:
    print(f"Product: {r['product_type']:18} | Lines: {r['line_count']:4} | Total Qty: {r['total_qty']:4} | Paid Qty: {r['paid_qty']:4} | Revenue: ₹{r['revenue']:,.2f}")

tot_q = sum(r['total_qty'] for r in rows)
tot_r = sum(r['revenue'] for r in rows)
print(f"\nSum across all categories (excluding AC outdoor): Total Qty = {tot_q}, Total Rev = ₹{tot_r:,.2f}")
