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

# Check all sales in PAVR for Aug 6-9
sql = """
SELECT 
    s.item_code,
    im.product,
    im.category,
    im.item_category,
    im.item_group,
    im.item_name,
    s.qty,
    s.sold_price
FROM azure_invoice_report inv
JOIN azure_sales_report s ON s.invoice_no = inv.invoice_no
JOIN item_master im ON im.item_code = s.item_code
WHERE inv.branch = 'PAVR'
  AND toDate(inv.date) >= '2026-08-06'
  AND toDate(inv.date) <= '2026-08-09'
  AND toFloat64(s.sold_price) > 0
"""
rows = ch_query(sql)
print(f"Total sales line items in PAVR Aug 6-9: {len(rows)}")

# Let's inspect potential matches for AC, Ref, WM, TV, Mobile, Laptop across all fields:
matches = {
    'TV': [],
    'Washing machine': [],
    'Referigerator': [],
    'Mobile': [],
    'Laptop': [],
    'AC': [],
    'Other': []
}

for r in rows:
    fields = [
        str(r.get('item_category') or '').lower(),
        str(r.get('category') or '').lower(),
        str(r.get('product') or '').lower(),
        str(r.get('item_name') or '').lower(),
        str(r.get('item_group') or '').lower()
    ]
    all_str = " ".join(fields)
    
    cat = str(r.get('item_category') or '').strip().lower()
    name = str(r.get('item_name') or '').strip().lower()
    prod = str(r.get('product') or '').strip().lower()
    
    qty = int(r.get('qty', 0))
    rev = float(r.get('sold_price', 0)) * qty
    
    # Check what category it matches based on user's rules:
    # "AC may be given as ac indoor , ac , Air conditioner , Referigerator may be given as Ref , Washing machine may be given as WM ,mobile and laptop will have the same name and rest all products should come under "other ""
    
    # Let's test checking item_category primarily and item_name/product
    assigned = None
    
    # TV:
    if 'tv' in cat or 'television' in cat or ' led ' in name or name.startswith('tv ') or ' tv' in name:
        assigned = 'TV'
    # WM:
    elif 'washing machine' in cat or cat == 'wm' or 'wm' in cat.split() or 'washing machine' in name:
        assigned = 'Washing machine'
    # Ref:
    elif 'refrigerator' in cat or 'fridge' in cat or cat == 'ref' or 'ref' in cat.split() or 'refrigerator' in name or 'fridge' in name:
        assigned = 'Referigerator'
    # Mobile:
    elif 'mobile' in cat or 'smartphone' in cat or 'phone' in cat or 'mobile' in name:
        assigned = 'Mobile'
    # Laptop:
    elif 'laptop' in cat or 'notebook' in cat or 'laptop' in name:
        assigned = 'Laptop'
    # AC:
    elif 'ac indoor' in cat or 'air conditioner' in cat or cat == 'ac' or 'ac' in cat.split() or 'ac outdoor' in cat or 'air conditioner' in name:
        assigned = 'AC'
    else:
        assigned = 'Other'
        
    matches[assigned].append((r, qty, rev))

for k in ['TV', 'Washing machine', 'Referigerator', 'Mobile', 'Laptop', 'AC', 'Other']:
    items = matches[k]
    total_qty = sum(x[1] for x in items)
    total_rev = sum(x[2] for x in items)
    print(f"[{k}]: {len(items)} items, total_qty={total_qty}, total_rev=₹{total_rev:,.2f}")
    if k in ['TV', 'Washing machine', 'Referigerator', 'Mobile', 'Laptop', 'AC'] and len(items) > 0:
        sample = items[:3]
        for s in sample:
            print(f"   Sample: cat='{s[0]['item_category']}' name='{s[0]['item_name']}' qty={s[1]} rev={s[2]}")
