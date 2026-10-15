import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Current campaigns table
c.execute("SELECT MAX(id) as max_id, MIN(id) as min_id, COUNT(*) as total FROM campaigns")
r = c.fetchone()
print(f"Campaigns: total={r['total']}, IDs range {r['min_id']} to {r['max_id']}")

# Revenue summary
c.execute("SELECT SUM(purchase_value) as total, COUNT(*) as cnt FROM campaigns WHERE purchase_value > 0")
r = c.fetchone()
print(f"Revenue: total={r['total']}, campaigns with revenue={r['cnt']}")

# campaign_customers current state
c.execute("SELECT campaign_id, COUNT(*) as cnt FROM campaign_customers GROUP BY campaign_id ORDER BY campaign_id")
cust_rows = c.fetchall()
print(f"\ncampaign_customers: {len(cust_rows)} distinct IDs, total rows = {sum(r['cnt'] for r in cust_rows)}")
orphans = []
for r in cust_rows:
    c2 = conn.cursor()
    c2.execute("SELECT campaign_name, type FROM campaigns WHERE id=?", (r['campaign_id'],))
    camp = c2.fetchone()
    status = f"{camp['campaign_name']} / {camp['type']}" if camp else "(ORPHAN)"
    if not camp:
        orphans.append(r['campaign_id'])
    print(f"  campaign_id={r['campaign_id']} | {status} | {r['cnt']:,} customers")

print(f"\nOrphaned campaign_ids: {orphans}")
conn.close()
