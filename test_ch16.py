import sqlite3
c = sqlite3.connect('campaign_dashboard.db').cursor()
print(c.execute("SELECT purchase_count, new_customers, existing_customers FROM campaigns WHERE campaign_name='All kerala RCS'").fetchone())
