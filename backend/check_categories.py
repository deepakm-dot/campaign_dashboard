"""
1. Check distinct categories in item_master (ClickHouse)
2. Check the branch mapping to fix the "branch not mapped" error
"""
import json, urllib.request, base64, openpyxl

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

# --- Check distinct categories in item_master ---
print("=" * 60)
print("ALL DISTINCT CATEGORIES in item_master:")
print("=" * 60)
rows = ch_query("SELECT DISTINCT category FROM item_master ORDER BY category")
for r in rows:
    print(f"  '{r.get('category','')}'")

# --- Check what branches exist in azure_invoice_report ---
print("\n" + "=" * 60)
print("ALL DISTINCT BRANCHES in azure_invoice_report:")
print("=" * 60)
rows2 = ch_query("SELECT DISTINCT branch FROM azure_invoice_report ORDER BY branch")
for r in rows2:
    print(f"  '{r.get('branch','')}'")

# --- Show Book1.xlsx contents ---
print("\n" + "=" * 60)
print("Book1.xlsx branch map:")
print("=" * 60)
try:
    wb = openpyxl.load_workbook('Book1.xlsx', data_only=True)
    ws = wb.active
    for row in ws.iter_rows(min_row=1, values_only=True):
        print(f"  code={row[0]}  name={row[1]}")
except Exception as e:
    print(f"  [ERROR] {e}")
