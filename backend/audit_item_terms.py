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

print("=== 1. Where do 'ac indoor', 'ref', 'wm' appear in item_master? ===")
# Search across item_category, category, product, item_group
queries = [
    ("item_category matching ac", "SELECT DISTINCT item_category FROM item_master WHERE lower(item_category) LIKE '%ac%' OR lower(item_category) LIKE '%air%'"),
    ("item_category matching ref", "SELECT DISTINCT item_category FROM item_master WHERE lower(item_category) LIKE '%ref%' OR lower(item_category) LIKE '%fridge%'"),
    ("item_category matching wm", "SELECT DISTINCT item_category FROM item_master WHERE lower(item_category) LIKE '%wm%' OR lower(item_category) LIKE '%wash%'"),
    ("product matching ac", "SELECT DISTINCT product FROM item_master WHERE lower(product) LIKE '%ac%' OR lower(product) LIKE '%air condition%'"),
    ("product matching ref", "SELECT DISTINCT product FROM item_master WHERE lower(product) LIKE '%ref%' OR lower(product) LIKE '%fridge%'"),
    ("product matching wm", "SELECT DISTINCT product FROM item_master WHERE lower(product) LIKE '%wm%' OR lower(product) LIKE '%wash%'"),
]

for title, q in queries:
    res = ch_query(q)
    print(f"\n--- {title} ({len(res)} results) ---")
    for r in res[:15]:
        print(" ", list(r.values())[0])

