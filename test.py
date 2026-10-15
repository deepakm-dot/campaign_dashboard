import sqlite3
import clickhouse_connect

conn = sqlite3.connect('campaign_dashboard.db')
c = conn.cursor()
c.execute('SELECT customer_mobile FROM campaign_customers WHERE campaign_id=31369')
mobiles = [r[0] for r in c.fetchall() if r[0]]

client = clickhouse_connect.get_client(host='localhost', port=8123, username='default', password='')

match_count_dates = 0
match_count_all = 0

for i in range(0, len(mobiles), 10000):
    chunk = mobiles[i:i+10000]
    m_list = ", ".join(f"'{m}'" for m in chunk)
    
    q1 = f"SELECT count(DISTINCT mobile) FROM default.azure_sales_report WHERE mobile IN ({m_list}) AND toDate(date) >= '2026-09-12' AND toDate(date) <= '2026-09-13'"
    match_count_dates += client.query(q1).result_rows[0][0]
    
    q2 = f"SELECT count(DISTINCT mobile) FROM default.azure_sales_report WHERE mobile IN ({m_list})"
    match_count_all += client.query(q2).result_rows[0][0]

print(f'Matches inside 12-13 Sept: {match_count_dates}')
print(f'Matches all time: {match_count_all}')
