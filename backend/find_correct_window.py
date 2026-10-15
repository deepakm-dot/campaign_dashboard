"""
Recompute fresh KPIs for Vypin and Paravoor Onam from ClickHouse.
Uses the same logic as calculate_kpis_for_campaign().
Compares with what's stored in SQLite to identify discrepancy.
"""
import sqlite3, json, urllib.request, base64
from datetime import datetime, timedelta

DB_FILE = 'campaign_dashboard.db'
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

conn = sqlite3.connect(DB_FILE)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check all campaigns that have purchase data
TARGET_IDS = [731, 732]   # Paravoor WhatsApp, Vypin WhatsApp

for cid in TARGET_IDS:
    cur.execute("SELECT * FROM campaigns WHERE id=?", (cid,))
    camp = dict(cur.fetchone())

    name   = camp['campaign_name']
    ctype  = camp['type']
    start  = camp['start_date'][:10]
    end    = (camp['end_date'] or start)[:10]
    budget = camp['budget'] or 0
    branch = (camp['branch_code'] or '').strip()

    # Compute date window (same logic as main.py)
    start_dt  = datetime.strptime(start, '%Y-%m-%d')
    end_dt    = datetime.strptime(end,   '%Y-%m-%d')
    if start_dt == end_dt:
        q_start = start
        q_end   = start
    else:
        q_start = start
        q_end   = (start_dt + timedelta(days=2)).strftime('%Y-%m-%d')

    print(f"\n{'='*60}")
    print(f"Campaign: {name} [{ctype}] id={cid}")
    print(f"  Sheet dates: {start} → {end}")
    print(f"  Query window: {q_start} → {q_end}")
    print(f"  Branch: '{branch}'  Budget: ₹{budget:,.0f}")
    print(f"  Stored KPIs: purchases={camp['purchase_count']} rev=₹{camp['purchase_value']:,.0f} roi=₹{camp['roi']:.0f}")

    # Get all mobiles
    cur.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?", (cid,))
    mobiles = [r['customer_mobile'] for r in cur.fetchall() if r['customer_mobile']]
    print(f"  Campaign customers (Drive file): {len(mobiles):,}")

    if not mobiles:
        print("  ⚠️ No customers linked — cannot verify from CH")
        continue

    branch_filter = f"AND branch = '{branch}'" if branch else ''

    # Test multiple windows
    windows = [
        (q_start, q_end,                                   f"Current window ({q_start}→{q_end})"),
        (start,   end,                                     f"Full campaign ({start}→{end})"),
        (start,   (start_dt+timedelta(days=7)).strftime('%Y-%m-%d'), f"Extended +7d"),
        (start,   (start_dt+timedelta(days=30)).strftime('%Y-%m-%d'),f"Full month"),
    ]

    for ws, we, label in windows:
        in_list = ",".join(f"'{m}'" for m in mobiles[:5000])
        sql = f"""
            SELECT COUNT(DISTINCT customer_mobile) as cust,
                   COUNT(DISTINCT invoice_no) as inv,
                   SUM(invoice_total) as rev
            FROM azure_invoice_report
            WHERE customer_mobile IN ({in_list})
              AND toDate(date) >= '{ws}' AND toDate(date) <= '{we}'
              {branch_filter}
        """
        rows = ch_query(sql)
        if rows:
            r = rows[0]
            cust = int(r.get('cust',0) or 0)
            inv  = int(r.get('inv',0) or 0)
            rev  = float(r.get('rev',0) or 0)
            roi  = rev / budget if budget > 0 else 0
            match = " ← MATCHES STORED!" if abs(rev - camp['purchase_value']) < 1000 else ""
            print(f"  {label}: cust={cust:3d}, inv={inv:4d}, rev=₹{rev:>12,.0f}, roi=₹{roi:.0f}{match}")

conn.close()
