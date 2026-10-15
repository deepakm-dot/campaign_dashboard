import sys
sys.path.append('backend')
from main import get_db, query_clickhouse

conn = get_db()
c = conn.cursor()

c.execute("SELECT id, campaign_name, start_date, end_date, budget, target_size, branch_code FROM campaigns WHERE campaign_name='Mannarkkad Future'")
camp = c.fetchone()

camp_id = camp['id']
camp_name = camp['campaign_name']
start_dt = camp['start_date'][:10]
end_dt = camp['end_date'][:10]
budget = float(camp['budget'] or 0)
sms_delivered = int(camp['target_size'] or 0)
branch = camp['branch_code']

print(f"Calculating for {camp_name} ({camp_id}), branch={branch}...")

c.execute("SELECT customer_mobile FROM campaign_customers WHERE campaign_id=?", (camp_id,))
mobiles = [r['customer_mobile'] for r in c.fetchall() if r['customer_mobile']]

branch_cond = f"branch = '{branch}'"
branch_filter = f"AND {branch_cond}" if branch else ""
unique_customers = {}
total_revenue = 0.0

for i in range(0, len(mobiles), 10000):
    chunk = mobiles[i:i+10000]
    mobile_list = ", ".join(f"'{m}'" for m in chunk)
    sql = (f"SELECT customer_mobile, "
           f"SUM(IF(toDate(date) >= '{start_dt}' AND toDate(date) <= '{end_dt}' {branch_filter}, invoice_total, 0)) as customer_total, "
           f"MAX(IF(toDate(date) >= '2020-01-01' AND toDate(date) < '{start_dt}', 1, 0)) as has_history "
           f"FROM azure_invoice_report "
           f"WHERE customer_mobile IN ({mobile_list}) "
           f"GROUP BY customer_mobile "
           f"HAVING customer_total > 0")
    
    for row in query_clickhouse(sql):
        mob = row.get('customer_mobile', '')
        if mob and mob not in unique_customers:
            unique_customers[mob] = {
                'total': float(row.get('customer_total', 0) or 0),
                'has_history': int(row.get('has_history', 0) or 0)
            }
            
purchase_count = len(unique_customers)
total_revenue = sum(v['total'] for v in unique_customers.values())
existing_customers = sum(1 for v in unique_customers.values() if v['has_history'] > 0)
new_customers = sum(1 for v in unique_customers.values() if v['has_history'] == 0)

conv_rate = (purchase_count / sms_delivered * 100) if sms_delivered > 0 else 0
roi = (total_revenue / budget) if budget > 0 else 0

print(f"  -> Rev=Rs.{total_revenue:,.0f} | Customers={purchase_count} (New: {new_customers}, Existing: {existing_customers}) | Conv={conv_rate:.2f}% | ROI={roi:.2f}x")

c.execute("""UPDATE campaigns SET purchase_count=?, purchase_value=?,
             conversion_rate=?, roi=?, budget=?, branch_code=?,
             new_customers=?, existing_customers=?
             WHERE id=?""",
          (purchase_count, total_revenue, conv_rate, roi, budget, branch, 
           new_customers, existing_customers, camp_id))
conn.commit()

# Now also calculate top_brands and top_categories using main.py logic
from main import calculate_kpis_for_campaign
print("Calculating top brands & categories...")
calculate_kpis_for_campaign(camp_id, start_dt, end_dt, budget)
print("Done!")
