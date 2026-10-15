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

# Check VPF products in ClickHouse grouped by Product
sql_vpf_prod_detail = """
SELECT 
    im.product as product,
    count() as lines,
    sum(s.qty) as net_qty,
    sumIf(s.qty, s.sold_price > 0) as paid_qty,
    sum(s.sold_price * s.qty) as net_rev,
    sumIf(s.sold_price * s.qty, s.sold_price > 0) as gross_rev
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY product
ORDER BY net_rev DESC
"""
rows = ch_query(sql_vpf_prod_detail)
print("=== All products in VPF by im.product ===")
for r in rows:
    print(f"  {str(r['product']):25s} | lines: {r['lines']:4d} | net_qty: {int(r['net_qty']):4d} | paid_qty: {int(r['paid_qty']):4d} | rev: Rs {float(r['net_rev']):12,.2f}")

# Total across all products in VPF
total_lines = sum(r['lines'] for r in rows)
total_net_qty = sum(int(r['net_qty']) for r in rows)
total_paid_qty = sum(int(r['paid_qty']) for r in rows)
total_net_rev = sum(float(r['net_rev']) for r in rows)
print(f"\nTOTAL VPF: lines={total_lines}, net_qty={total_net_qty}, paid_qty={total_paid_qty}, net_rev=Rs {total_net_rev:,.2f}")
