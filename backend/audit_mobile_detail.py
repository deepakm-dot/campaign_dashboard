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

sql = """
SELECT 
    s.item_code, 
    im.product, 
    im.category, 
    im.item_category, 
    im.item_name, 
    toInt64(s.qty) as qty, 
    toFloat64(s.sold_price) as price, 
    s.invoice_no, 
    s.date
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND (
      im.product = 'MOBILE'
      OR lower(im.item_category) IN ('mobile', 'mobiles', 'mobile smart phone', 'mobile feature phone', 'mobile gsm phone')
      OR lower(im.product) LIKE '%mobile%'
  )
ORDER BY s.date, s.invoice_no
"""

rows = ch_query(sql)
print(f"Total rows matched: {len(rows)}")

# Breakdown by product field
by_prod = {}
for r in rows:
    p = r['product']
    by_prod[p] = by_prod.get(p, 0) + r['qty']

print("Breakdown by im.product:")
for p, q in sorted(by_prod.items()):
    print(f"  {p}: {q}")

# Look at rows where im.product == 'MOBILE'
mob_rows = [r for r in rows if r['product'] == 'MOBILE']
print(f"\nRows where im.product == 'MOBILE': {len(mob_rows)}, total qty = {sum(r['qty'] for r in mob_rows)}")

# Let's inspect price <= 0 or other types
print("\nItems with im.product == 'MOBILE':")
zero_or_neg = []
for r in mob_rows:
    if r['price'] <= 0:
        zero_or_neg.append(r)

print(f"Zero or negative price items in im.product == 'MOBILE': {len(zero_or_neg)}")
for r in zero_or_neg:
    print(f"  {r['date'][:10]} | {r['invoice_no']} | price={r['price']} | qty={r['qty']} | {r['item_name']}")

# What if im.product == 'MOBILE' (112 items)?
# Total rows where im.product == 'MOBILE':
print(f"\nExact count of rows with im.product == 'MOBILE': {len(mob_rows)}")
