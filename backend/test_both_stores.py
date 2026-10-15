import json, urllib.request, base64, re, sqlite3

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

branches = ch_query("SELECT code, branch_name, district FROM branch_master")

def resolve_branch(camp_name):
    name_clean = (camp_name or '').lower()
    words = re.findall(r'[a-zA-Z]{3,}', name_clean)
    skip = {'onam', 'offers', 'offer', 'campaign', 'special', 'support', 'august', 'freedom', 'sale', 'inauguration', 'split', 'voice', 'wtsp', 'whatsapp', 'call', 'rcs'}
    kws = [w for w in words if w not in skip]
    for kw in kws:
        matches = [b for b in branches if kw in b['branch_name'].lower() and 'godown' not in b['branch_name'].lower() and 'warehouse' not in b['branch_name'].lower()]
        if matches:
            exact = [b for b in matches if re.search(r'\b' + kw + r'\b', b['branch_name'].lower())]
            match = exact[0] if exact else matches[0]
            return match['code'], match['branch_name']
    return '', ''

def get_store_sales(branch, start_date, end_date):
    sql = f"""
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
        sumIf(toInt64(s.qty), s.sold_price > 0) as paid_qty,
        sum(toInt64(s.qty)) as net_qty,
        sum(toFloat64(s.sold_price) * toInt64(s.qty)) as net_revenue,
        sumIf(toFloat64(s.sold_price) * toInt64(s.qty), s.sold_price > 0) as gross_rev,
        sumIf(toFloat64(s.sold_price) * toInt64(s.qty), s.sold_price < 0) as deductions
    FROM azure_sales_report s
    LEFT JOIN item_master im ON im.item_code = s.item_code
    WHERE s.branch = '{branch}'
      AND toDate(s.date) >= '{start_date}'
      AND toDate(s.date) <= '{end_date}'
    GROUP BY product_type
    ORDER BY net_revenue DESC
    """
    return ch_query(sql)

for cid, cname in [(731, 'Paravoor Onam Offers'), (732, 'Vypin Onam Offers')]:
    bcode, bname = resolve_branch(cname)
    print(f"\n==========================================")
    print(f"Campaign: {cname} (ID: {cid})")
    print(f"Resolved Branch: {bname} ({bcode})")
    print(f"==========================================")
    rows = get_store_sales(bcode, '2026-08-06', '2026-08-09')
    tot_rev = sum(float(r['net_revenue']) for r in rows)
    tot_paid_qty = sum(int(r['paid_qty']) for r in rows)
    tot_net_qty = sum(int(r['net_qty']) for r in rows)
    for r in rows:
        print(f"  {r['product_type']:18s} | paid_qty: {int(r['paid_qty']):3d} | net_qty: {int(r['net_qty']):3d} | rev: Rs {float(r['net_revenue']):12,.2f}")
    print(f"  TOTAL: paid_qty={tot_paid_qty}, net_qty={tot_net_qty}, net_revenue=Rs {tot_rev:,.2f}")
