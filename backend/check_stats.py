import sqlite3

conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

try:
    c.execute("SELECT * FROM config")
    rows = c.fetchall()
    print("=== CONFIG TABLE ===")
    for r in rows:
        print(dict(r))
except Exception as e:
    print(f"Error querying config: {e}")

c.execute("SELECT COUNT(*) FROM campaigns")
total_campaigns = c.fetchone()[0]

c.execute("SELECT value FROM config WHERE key='total_audience_reached'")
row_cfg = c.fetchone()
cfg_reached = row_cfg['value'] if row_cfg else None

c.execute("SELECT COALESCE(SUM(target_size),0) FROM campaigns WHERE target_size > 0")
sum_reached = c.fetchone()[0]

c.execute("""
    SELECT COALESCE(SUM(purchase_value), 0) as total_sales,
           COALESCE(AVG(roi), 0)            as avg_roi
    FROM campaigns
    WHERE purchase_value > 0
""")
row_sales = dict(c.fetchone())

print("\n=== DASHBOARD STATS ===")
print(f"Total campaigns: {total_campaigns}")
print(f"Config reached: {cfg_reached}")
print(f"Sum target_size: {sum_reached}")
print(f"Total sales: ₹{row_sales['total_sales']:,.2f}")
print(f"Avg ROI: ₹{row_sales['avg_roi']:,.2f}")
