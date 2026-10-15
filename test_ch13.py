import sqlite3
c = sqlite3.connect('campaign_dashboard.db').cursor()
c.execute("UPDATE campaigns SET branch_code='MKF' WHERE campaign_name='Mannarkkad Future'")
c.connection.commit()
print("Updated Mannarkkad Future branch_code to MKF")
