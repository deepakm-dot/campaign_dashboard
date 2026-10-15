import sys
sys.path.append('backend')
import sqlite3
import json
from main import calculate_kpis_for_campaign, get_db

conn = get_db()
c = conn.cursor()
c.execute("SELECT id, start_date, end_date, budget FROM campaigns WHERE campaign_name='Mannarkkad Future'")
row = c.fetchone()

camp_id = row['id']
start_dt = row['start_date']
end_dt = row['end_date']
budget = row['budget']

print(f"Recalculating KPIs for Mannarkkad Future (ID: {camp_id})")
calculate_kpis_for_campaign(camp_id, start_dt, end_dt, budget)
print("Done!")
