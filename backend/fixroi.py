import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()

# Fix ROI = revenue / actual_cost (correct formula confirmed by user)
c.execute('UPDATE campaigns SET roi = purchase_value / budget WHERE budget > 0 AND purchase_value > 0')
print(f'Updated {c.rowcount} campaigns with correct ROI')

c.execute('SELECT campaign_name, type, purchase_value, budget, roi FROM campaigns WHERE purchase_value > 0 ORDER BY purchase_value DESC')
for r in c.fetchall():
    print(f"  {r[0]} | {r[1]} | Revenue=Rs.{r[2]:,.0f} | Budget=Rs.{r[3]:,.0f} | ROI=Rs.{r[4]:.0f}")

conn.commit()
conn.close()
print('Done.')
