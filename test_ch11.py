import sqlite3
c = sqlite3.connect('campaign_dashboard.db').cursor()
print(c.execute("SELECT branch_code FROM campaigns WHERE campaign_name='Mannarkkad Future'").fetchone())
