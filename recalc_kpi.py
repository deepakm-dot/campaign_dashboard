import sys
sys.path.append('backend')
import main
import sqlite3

conn = main.get_db()
c = conn.cursor()

c.execute("SELECT id, start_date, end_date, budget FROM campaigns")
campaigns = c.fetchall()

print(f"Recalculating KPIs for {len(campaigns)} campaigns...")
for camp in campaigns:
    camp_id = camp['id']
    start_date = camp['start_date']
    end_date = camp['end_date']
    budget = camp['budget']
    
    print(f"Calculating for {camp_id}...")
    try:
        main.calculate_kpis_for_campaign(c, camp_id, start_date, end_date, budget)
    except Exception as e:
        print(f"Failed for {camp_id}: {e}")

conn.commit()
print("Done!")
