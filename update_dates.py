import sqlite3
conn = sqlite3.connect('backend/campaign_dashboard.db')
c = conn.cursor()
c.execute("UPDATE campaigns SET end_date='2026-08-09' WHERE id IN (731, 732, 738, 739)")
conn.commit()
print("Restored end_date to 2026-08-09")
