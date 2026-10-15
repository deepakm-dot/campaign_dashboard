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

print("=== Branches in branch_master matching Paravoor / Paravur ===")
rows = ch_query("""
    SELECT code, branch_name, district, store_type, mapped_warehouse
    FROM branch_master
    WHERE lower(branch_name) LIKE '%parav%'
       OR lower(code) LIKE '%pav%'
       OR lower(code) LIKE '%par%'
""")
for r in rows:
    print(r)

print("\n=== Check ALL branches that have 'Paravur' or 'Paravoor' anywhere in address or name ===")
rows2 = ch_query("""
    SELECT code, branch_name, address, district, store_type
    FROM branch_master
    WHERE lower(branch_name) LIKE '%parav%'
       OR lower(address) LIKE '%parav%'
""")
for r in rows2:
    print(r)
