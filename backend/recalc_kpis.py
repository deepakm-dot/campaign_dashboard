"""
Recalculate and UPDATE KPIs for all campaigns that have customers linked,
using the correct window: start_date to start_date + 2 days.
This WRITES the fresh ClickHouse values back to SQLite.
ROI = purchase_value / budget  (exact formula confirmed by user)
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

# Get all campaigns with linked customers
cur.execute("""
    SELECT DISTINCT cc.campaign_id, c.campaign_name, c.type,
                    c.start_date, c.end_date, c.budget, c.branch_code,
                    c.purchase_count, c.purchase_value, c.roi
    FROM campaign_customers cc
    JOIN campaigns c ON c.id = cc.campaign_id
    ORDER BY c.campaign_name
""")
camps = [dict(r) for r in cur.fetchall()]
print(f"Found {len(camps)} campaigns with linked customers\n")

updated = 0
for camp in camps:
    cid    = camp['campaign_id']
    name   = camp['campaign_name']
    ctype  = camp['type']
    start  = (camp['start_date'] or '')[:10]
    end    = (camp['end_date'] or start)[:10]
    budget = camp['budget'] or 0
    branch = (camp['branch_code'] or '').strip()

    # Date window: start to start+2 days (confirmed by user)
    try:
        sd = datetime.strptime(start, '%Y-%m-%d')
        q_start = start
        q_end   = (sd + timedelta(days=2)).strftime('%Y-%m-%d')
    except Exception:
        q_start = start
        q_end   = start

    # Get mobiles
    cur.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?", (cid,))
    mobiles = [r['customer_mobile'] for r in cur.fetchall() if r['customer_mobile']]
    if not mobiles:
        continue

    branch_filter = f"AND branch = '{branch}'" if branch else ''

    # Query ClickHouse in chunks of 10000
    total_rev  = 0.0
    total_cust = 0
    total_inv  = 0
    chunk_size = 10000

    for i in range(0, len(mobiles), chunk_size):
        chunk = mobiles[i:i+chunk_size]
        in_list = ",".join(f"'{m}'" for m in chunk)
        sql = f"""
            SELECT COUNT(DISTINCT customer_mobile) as cust,
                   COUNT(DISTINCT invoice_no)      as inv,
                   SUM(invoice_total)              as rev
            FROM azure_invoice_report
            WHERE customer_mobile IN ({in_list})
              AND toDate(date) >= '{q_start}'
              AND toDate(date) <= '{q_end}'
              {branch_filter}
        """
        rows = ch_query(sql)
        if rows:
            r = rows[0]
            total_rev  += float(r.get('rev',0)  or 0)
            total_cust += int(r.get('cust',0)   or 0)
            total_inv  += int(r.get('inv',0)    or 0)

    roi = total_rev / budget if budget > 0 else 0

    old_rev  = camp['purchase_value'] or 0
    old_cnt  = camp['purchase_count'] or 0
    old_roi  = camp['roi'] or 0

    changed = abs(total_rev - old_rev) > 1 or total_cust != old_cnt
    flag = " ← CHANGED" if changed else ""
    print(f"  id={cid:4d} | {name[:35]:35s} | {ctype:12s}")
    print(f"    Window: {q_start}→{q_end}  Branch: '{branch}'")
    print(f"    Old: purchases={old_cnt:4d}, rev=₹{old_rev:>12,.0f}, roi=₹{old_roi:.0f}")
    print(f"    New: purchases={total_cust:4d}, rev=₹{total_rev:>12,.0f}, roi=₹{roi:.0f}{flag}")
    print()

    # Update SQLite
    cur.execute("""
        UPDATE campaigns
        SET purchase_count=?, purchase_value=?, roi=?,
            conversion_rate=?
        WHERE id=?
    """, (
        total_cust,
        total_rev,
        round(roi, 2),
        round((total_cust / len(mobiles) * 100), 4) if mobiles else 0,
        cid
    ))
    if changed:
        updated += 1

conn.commit()
conn.close()
print(f"\n✅ Done. Updated {updated} campaigns with fresh ClickHouse values.")
print("Restart the server to reflect new values in the dashboard.")
