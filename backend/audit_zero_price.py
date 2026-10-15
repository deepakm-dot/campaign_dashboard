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

# Check items with sold_price == 0 vs sold_price > 0
sql = """
SELECT 
    s.item_code,
    s.qty,
    s.mop,
    s.sold_price,
    s.taxable,
    im.item_name,
    im.category,
    im.item_category,
    im.product,
    im.item_group
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'PAVR'
  AND toDate(s.date) >= '2026-08-06'
  AND toDate(s.date) <= '2026-08-09'
  AND s.sold_price = 0
"""
zero_price_items = ch_query(sql)
print(f"Items with sold_price = 0: {len(zero_price_items)}")
from collections import Counter
cat_counter = Counter()
for item in zero_price_items:
    cat_counter[f"{item.get('category')} | {item.get('item_category')} | {item.get('item_name')}"] += 1

print("\nSample zero-price items:")
for k, count in cat_counter.most_common(20):
    print(f"  {count:3d} x {k}")
