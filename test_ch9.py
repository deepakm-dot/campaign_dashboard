import sqlite3
c = sqlite3.connect('campaign_dashboard.db').cursor()
print(c.execute("SELECT id, purchase_count, existing_customers, new_customers FROM campaigns WHERE campaign_name='Palakkad Future'").fetchall())
print(c.execute("SELECT id, purchase_count, existing_customers, new_customers FROM campaigns WHERE campaign_name='Thiruvalla Future'").fetchall())
print(c.execute("SELECT id, purchase_count, existing_customers, new_customers FROM campaigns WHERE campaign_name='Thondayad Future'").fetchall())
print(c.execute("SELECT id, purchase_count, existing_customers, new_customers FROM campaigns WHERE campaign_name='Marine Drive'").fetchall())
