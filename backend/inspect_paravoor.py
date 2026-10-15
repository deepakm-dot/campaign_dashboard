import sqlite3

conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT id, campaign_name, type, campaign_group, start_date, end_date, branch_code, target_size, purchase_count, purchase_value, roi FROM campaigns WHERE campaign_name LIKE '%Paravoor%'")
rows = c.fetchall()
print(f"Found {len(rows)} campaigns:")
for r in rows:
    print(dict(r))
