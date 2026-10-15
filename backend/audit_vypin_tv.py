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

print("=== 1. Branch Master Search for Vypin ===")
branches = ch_query("SELECT code, branch_name, category, store_type, district FROM branch_master WHERE lower(branch_name) LIKE '%vypin%' OR lower(code) LIKE '%vky%' OR lower(code) LIKE '%vpf%'")
for b in branches:
    print(b)

print("\n=== 2. Check TV sales in VKY vs VPF from Aug 6 to Aug 9, 2026 ===")
for br in ['VKY', 'VPF']:
    sql = f"""
    SELECT 
        toDate(s.date) as dt,
        count() as lines,
        sum(s.qty) as tv_qty,
        sum(s.sold_price * s.qty) as tv_revenue
    FROM azure_sales_report s
    LEFT JOIN item_master im ON im.item_code = s.item_code
    WHERE s.branch = '{br}'
      AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
      AND (im.product = 'TV' 
           OR lower(im.item_category) IN ('tv', 'tv 18 %', 'tv 28 %', 'signage tv')
           OR lower(im.category) = 'consumer electronics' AND lower(im.product) = 'tv')
    GROUP BY dt ORDER BY dt
    """
    rows = ch_query(sql)
    print(f"\nBranch {br} TV sales:")
    tot_qty = sum(float(r['tv_qty']) for r in rows)
    tot_rev = sum(float(r['tv_revenue']) for r in rows)
    for r in rows:
        print(f"  {r['dt']}: qty={r['tv_qty']}, rev=Rs {float(r['tv_revenue']):,.2f}")
    print(f"  Total TV for {br}: {tot_qty} units, Rs {tot_rev:,.2f}")
