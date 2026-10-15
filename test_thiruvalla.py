import sqlite3
c = sqlite3.connect('campaign_dashboard.db').cursor()
c.execute("SELECT id, campaign_name, target_size, type FROM campaigns WHERE campaign_name LIKE '%Thiruvalla%'")
for r in c.fetchall():
    print(r)
