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

# Check item_category in item_master matching ac, ref, wm, tv, mobile, laptop
sql = """
SELECT DISTINCT item_category, category
FROM item_master
WHERE lower(item_category) LIKE '%ac%'
   OR lower(item_category) LIKE '%air%'
   OR lower(item_category) LIKE '%ref%'
   OR lower(item_category) LIKE '%wm%'
   OR lower(item_category) LIKE '%wash%'
   OR lower(item_category) LIKE '%tv%'
   OR lower(item_category) LIKE '%mobile%'
   OR lower(item_category) LIKE '%laptop%'
ORDER BY item_category
"""
rows = ch_query(sql)
print("=== All matching item_category in item_master ===")
for r in rows:
    print(f"  {r['item_category']}  ({r['category']})")
