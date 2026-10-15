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
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.read().decode('utf-8'))
        return []

sql = """
SELECT 
    s.invoice_no,
    s.item_code,
    s.qty,
    s.sold_price,
    im.item_name
FROM azure_sales_report s
LEFT JOIN item_master im ON im.item_code = s.item_code
WHERE s.branch = 'VPF' AND toDate(s.date) BETWEEN '2026-08-06' AND '2026-08-09'
  AND s.sold_price < 0
"""
rows = ch_query(sql)
print(f"Total negative rows in VPF: {len(rows)}")
sr_tot = 0
ex_tot = 0
for r in rows:
    p = float(r['sold_price']) * float(r['qty'])
    inv = r['invoice_no']
    if '-SR-' in inv:
        sr_tot += p
        print(f"  RETURN: {inv} | {r['item_code']} | {p} | {r.get('item_name')}")
    else:
        ex_tot += p
        print(f"  EXCHANGE: {inv} | {r['item_code']} | {p} | {r.get('item_name')}")

print(f"\nTotal Returns for VPF: Rs {sr_tot:,.2f}")
print(f"Total Exchanges for VPF: Rs {ex_tot:,.2f}")
print(f"Total Deductions: Rs {(sr_tot + ex_tot):,.2f}")
