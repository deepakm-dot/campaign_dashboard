import sqlite3
c = sqlite3.connect('campaign_dashboard.db').cursor()
c.execute("DELETE FROM campaign_customers WHERE campaign_id = (SELECT id FROM campaigns WHERE campaign_name = 'All kerala RCS')")
c.execute("UPDATE campaigns SET purchase_count=0, purchase_value=0, new_customers=0, existing_customers=0 WHERE campaign_name = 'All kerala RCS'")
c.connection.commit()
print('Cleared campaign_customers for All kerala RCS')
