import sqlite3
from main import resolve_branch_from_clickhouse

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("SELECT id, campaign_name FROM campaigns")
rows = c.fetchall()

updated = 0
for cid, name in rows:
    code, bname = resolve_branch_from_clickhouse(name)
    if code:
        c.execute("UPDATE campaigns SET branch_code=? WHERE id=?", (code, cid))
        updated += 1
conn.commit()
conn.close()
print(f"Successfully populated branch_code for {updated} / {len(rows)} campaigns.")
