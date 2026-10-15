import sqlite3

DB_FILE = 'campaign_dashboard.db'
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

c.execute("DELETE FROM campaign_customers WHERE campaign_id=31325")
c.execute("UPDATE campaigns SET purchase_count=0, purchase_value=0, roi=0 WHERE id=31325")
conn.commit()
print("Successfully deleted the incorrect Kottayam data for Kottakkal Future (campaign 31325). The next sync will download the correct file.")
