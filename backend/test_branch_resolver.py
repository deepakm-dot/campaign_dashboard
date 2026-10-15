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

# Load all branches from branch_master into memory cache
branches = ch_query("SELECT code, branch_name, district FROM branch_master")
print(f"Loaded {len(branches)} branches from ClickHouse branch_master")

def match_branch(camp_name):
    name_clean = camp_name.lower()
    # Filter tokens
    words = re.findall(r'[a-zA-Z]{3,}', name_clean)
    skip_words = {'onam', 'offers', 'offer', 'campaign', 'special', 'support', 'august', 'freedom', 'sale', 'inauguration'}
    keywords = [w for w in words if w not in skip_words]
    
    for kw in keywords:
        # Match against branch_name in ClickHouse
        # Prefer direct branch (not godown/warehouse)
        matches = [b for b in branches if kw in b['branch_name'].lower() and 'godown' not in b['branch_name'].lower() and 'warehouse' not in b['branch_name'].lower()]
        if matches:
            # If multiple, prefer exact word match or FUTURE store
            exact = [b for b in matches if re.search(r'\b' + kw + r'\b', b['branch_name'].lower())]
            if exact:
                return exact[0]['code'], exact[0]['branch_name']
            return matches[0]['code'], matches[0]['branch_name']
    return None, None

# Test on SQLite campaigns
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT DISTINCT campaign_name FROM campaigns")
for r in c.fetchall():
    cname = r['campaign_name']
    code, bname = match_branch(cname)
    print(f"'{cname}' -> code: {code}, name: {bname}")
conn.close()
