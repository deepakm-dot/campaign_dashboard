import json, urllib.request, base64

CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def ch_query(sql):
    req = urllib.request.Request(CH_URL)
    token = base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode()
    req.add_header('Authorization', 'Basic ' + token)
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()).get('data', [])
    except Exception as e:
        print(f"Error: {e}")
        return []

print("=== azure_invoice_report columns ===")
for c in ch_query("DESCRIBE azure_invoice_report"):
    print(f"  {c.get('name')}: {c.get('type')}")

print("\n=== azure_sales_report columns ===")
for c in ch_query("DESCRIBE azure_sales_report"):
    print(f"  {c.get('name')}: {c.get('type')}")

print("\n=== item_master columns ===")
for c in ch_query("DESCRIBE item_master"):
    print(f"  {c.get('name')}: {c.get('type')}")
