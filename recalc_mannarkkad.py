import sys
sys.path.append('backend')
import main

conn = main.get_db()
c = conn.cursor()
c.execute("SELECT id FROM campaigns WHERE campaign_name='Mannarkkad Future'")
camp_id = c.fetchone()['id']

main.calculate_kpis_for_campaign(camp_id)
print("Finished recalculating for Mannarkkad Future")
