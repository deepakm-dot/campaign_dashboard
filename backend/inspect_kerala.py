import sqlite3

conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

rows = c.execute("SELECT id, campaign_name, type, campaign_group, data_source, start_date, end_date, sl_no, sheet_tab, target_size, purchase_count, purchase_value, conversion_rate, roi, existing_customers, new_customers FROM campaigns WHERE campaign_name LIKE '%kerala%'").fetchall()
for r in rows:
    print(dict(r))
