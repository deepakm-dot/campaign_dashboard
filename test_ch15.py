import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute("UPDATE campaigns SET branch_code='', purchase_count=0, purchase_value=0, new_customers=0, existing_customers=0 WHERE campaign_name='All kerala RCS'")
conn.commit()
print('Cleared All kerala RCS')
