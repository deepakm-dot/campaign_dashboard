import sqlite3

DB_FILE = 'campaign_dashboard.db'
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM campaign_customers WHERE campaign_id=31325")
count = c.fetchone()[0]
print(f"Deleting {count} rows for campaign 31325...")

c.execute("DELETE FROM campaign_customers WHERE campaign_id=31325")
c.execute("UPDATE campaigns SET purchase_count=0, purchase_value=0, roi=0 WHERE id=31325")
conn.commit()
print("Done.")
