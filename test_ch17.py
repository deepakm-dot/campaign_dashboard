import sys, sqlite3
sys.path.append('backend')
from main import get_db, query_clickhouse, calculate_kpis_for_campaign

conn = get_db()
c = conn.cursor()
c.execute("SELECT id, start_date, end_date, budget FROM campaigns WHERE campaign_name='All kerala RCS'")
camp = c.fetchone()
print(camp)
print("Running calculate_kpis_for_campaign...")
calculate_kpis_for_campaign(c, camp['id'], camp['start_date'], camp['end_date'], camp['budget'])
conn.commit()

c.execute("SELECT purchase_count, purchase_value, branch_code FROM campaigns WHERE campaign_name='All kerala RCS'")
print(c.fetchone())
