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
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')[:300]}")
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []

print("=== 1. Branch search ===")
branches = ch_query("SELECT code, branch_name, district FROM branch_master WHERE lower(branch_name) LIKE '%parav%' OR lower(code) LIKE '%pav%'")
for b in branches:
    print(b)

print("\n=== 2. SQLite campaign info for Paravoor ===")
import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT id, campaign_name, type, start_date, end_date, target_size, purchase_count, purchase_value, branch_code FROM campaigns WHERE lower(campaign_name) LIKE '%parav%'")
for r in c.fetchall():
    print(dict(r))
conn.close()

print("\n=== 3. Date check in azure_sales_report vs azure_invoice_report for PAVR ===")
sql_dates = """
SELECT 
    toDate(date) as dt,
    COUNT(DISTINCT invoice_no) as invoices,
    COUNT() as line_items,
    SUM(qty) as total_qty,
    SUM(sold_price * qty) as total_sold_price_val,
    SUM(taxable) as total_taxable
FROM azure_sales_report
WHERE branch = 'PAVR' AND toDate(date) BETWEEN '2026-08-01' AND '2026-08-15'
GROUP BY dt ORDER BY dt
"""
for r in ch_query(sql_dates):
    print(r)

print("\n=== 4. Check if invoice_total matches sum(sold_price * qty) ===")
sql_inv = """
SELECT 
    toDate(inv.date) as dt,
    COUNT(DISTINCT inv.invoice_no) as inv_count,
    SUM(inv.invoice_total) as sum_invoice_total,
    SUM(inv.discount) as sum_discount,
    SUM(inv.exchange) as sum_exchange
FROM azure_invoice_report inv
WHERE inv.branch = 'PAVR' AND toDate(inv.date) BETWEEN '2026-08-06' AND '2026-08-09'
GROUP BY dt ORDER BY dt
"""
for r in ch_query(sql_inv):
    print(r)

