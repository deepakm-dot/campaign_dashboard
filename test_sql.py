import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
for r in c.execute("SELECT id, campaign_name, branch_code, target_size, purchase_count FROM campaigns WHERE campaign_name LIKE '%Kanjirappally%'"):
    print(r)
