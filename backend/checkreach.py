import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Total audience reached
c.execute('SELECT COALESCE(SUM(target_size),0) as total, COUNT(*) as cnt FROM campaigns WHERE target_size > 0')
r = c.fetchone()
print(f"Total target_size (Audience Reached): {r['total']:,.0f} ({r['total']/1e6:.2f}M)")
print(f"Campaigns with target_size set: {r['cnt']}")
print()

# Show all campaigns with target_size, sorted by size
c.execute('SELECT id, campaign_name, type, start_date, target_size FROM campaigns WHERE target_size > 0 ORDER BY target_size DESC')
rows = c.fetchall()
print(f"{'ID':<6} {'target_size':>12}  {'Campaign Name':<50} {'Type':<12} {'Date'}")
print('-'*100)
for r in rows:
    print(f"{r['id']:<6} {r['target_size']:>12,.0f}  {r['campaign_name']:<50} {r['type']:<12} {r['start_date']}")

conn.close()
