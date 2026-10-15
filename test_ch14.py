import sqlite3
c = sqlite3.connect('campaign_dashboard.db').cursor()
print(c.execute("SELECT purchase_count, purchase_value FROM campaigns WHERE campaign_name='Mannarkkad Future'").fetchone())
