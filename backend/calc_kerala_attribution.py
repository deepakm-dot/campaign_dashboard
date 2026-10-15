import sqlite3
import json
import urllib.request
import base64

DB_FILE = 'campaign_dashboard.db'
CH_URL  = "https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/"
CH_USER = "default"
CH_PASS = "ZFlujj9SA_Iei"

def query_clickhouse(sql):
    req = urllib.request.Request(CH_URL)
    req.add_header('Authorization', 'Basic ' + base64.b64encode(f"{CH_USER}:{CH_PASS}".encode()).decode())
    req.add_header('Content-Type', 'text/plain')
    req.data = (sql + " FORMAT JSON").encode()
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode()).get('data', [])

def process_campaign(c, conn, camp_id):
    camp = c.execute("SELECT * FROM campaigns WHERE id=?", (camp_id,)).fetchone()
    if not camp:
        print(f"Campaign {camp_id} not found!")
        return

    camp_name = camp['campaign_name']
    start_dt = camp['start_date']
    end_dt = camp['end_date']
    sms_delivered = camp['target_size'] or 0
    budget = camp['budget'] or 0
    branch = camp['branch_code'] or ''

    print(f"\nProcessing [{camp_id}] {camp_name} ({camp['campaign_group']}) {start_dt} to {end_dt}...")

    # 1. Fetch store/state purchasers from ClickHouse for the date window
    branch_filter = f"AND branch = '{branch}'" if branch else ""
    sql_purchasers = (f"SELECT customer_mobile, SUM(invoice_total) as customer_total "
                      f"FROM azure_invoice_report "
                      f"WHERE toDate(date) >= '{start_dt}' AND toDate(date) <= '{end_dt}' {branch_filter} "
                      f"GROUP BY customer_mobile "
                      f"HAVING customer_total > 0")
    print(f"  Fetching ClickHouse purchasers ({start_dt} to {end_dt})...", flush=True)
    purchasers = query_clickhouse(sql_purchasers)
    print(f"  Found {len(purchasers)} unique purchasers in ClickHouse.", flush=True)
    purchaser_map = {r['customer_mobile']: float(r.get('customer_total', 0) or 0) for r in purchasers if r.get('customer_mobile')}
    purchaser_mobiles = list(purchaser_map.keys())

    # 2. Match with SQLite campaign_customers
    matched_mobiles = set()
    for j in range(0, len(purchaser_mobiles), 5000):
        ch = purchaser_mobiles[j:j+5000]
        ph = ",".join("?" * len(ch))
        c.execute(f"SELECT customer_mobile FROM campaign_customers WHERE campaign_id=? AND customer_mobile IN ({ph})", [camp_id] + ch)
        for r in c.fetchall():
            matched_mobiles.add(r[0])
    
    print(f"  Matched campaign audience purchasers: {len(matched_mobiles)}", flush=True)

    # 3. New vs Repeat customers
    repeat_customers = set()
    matched_list = list(matched_mobiles)
    for j in range(0, len(matched_list), 10000):
        ch = matched_list[j:j+10000]
        m_str = ", ".join(f"'{m}'" for m in ch)
        hist_sql = (f"SELECT DISTINCT customer_mobile FROM azure_invoice_report "
                    f"WHERE customer_mobile IN ({m_str}) "
                    f"  AND toDate(date) >= '2020-01-01' AND toDate(date) < '{start_dt}'")
        for r in query_clickhouse(hist_sql):
            repeat_customers.add(r.get('customer_mobile'))

    purchase_count = len(matched_mobiles)
    total_revenue = sum(purchaser_map[m] for m in matched_mobiles)
    existing_customers = len(repeat_customers)
    new_customers = purchase_count - existing_customers

    conv_rate = (purchase_count / sms_delivered * 100) if sms_delivered > 0 else 0
    roi = (total_revenue / budget) if budget > 0 else 0

    print(f"  Results: Rev=Rs.{total_revenue:,.2f} | Count={purchase_count} (New: {new_customers}, Repeat: {existing_customers}) | Conv={conv_rate:.2f}% | ROI={roi:.2f}x")

    # 4. Top Brands & Categories
    inv_filter = f"toDate(s.date) >= '{start_dt}' AND toDate(s.date) <= '{end_dt}'"
    b_cond_ch = f"AND s.branch = '{branch}'" if branch else ""
    b_sql = f"""
    SELECT coalesce(nullIf(trim(im.brand), ''), 'Unknown') AS brand,
           SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
           SUM(if(toFloat64(s.sold_price) < 0, -toInt64(s.qty), toInt64(s.qty))) as qty
    FROM azure_sales_report s
    JOIN item_master im ON s.item_code = im.item_code
    WHERE {inv_filter} {b_cond_ch}
      AND im.product != 'AC OUTDOOR' AND im.product != 'SCHEME'
    GROUP BY brand ORDER BY revenue DESC LIMIT 5
    """
    top_brands = [{'brand': r.get('brand',''), 'revenue': float(r.get('revenue',0)), 'qty': int(r.get('qty',0))} for r in query_clickhouse(b_sql)]

    c_sql = f"""
    SELECT coalesce(nullIf(trim(im.product), ''), 'Unknown') AS category,
           SUM(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
           SUM(if(toFloat64(s.sold_price) < 0, -toInt64(s.qty), toInt64(s.qty))) as qty
    FROM azure_sales_report s
    JOIN item_master im ON s.item_code = im.item_code
    WHERE {inv_filter} {b_cond_ch}
      AND im.product != 'AC OUTDOOR' AND im.product != 'SCHEME'
    GROUP BY category ORDER BY revenue DESC LIMIT 5
    """
    top_cats = [{'category': r.get('category',''), 'revenue': float(r.get('revenue',0)), 'qty': int(r.get('qty',0))} for r in query_clickhouse(c_sql)]

    c.execute("""UPDATE campaigns SET purchase_count=?, purchase_value=?,
                 conversion_rate=?, roi=?, budget=?, branch_code=?,
                 new_customers=?, existing_customers=?,
                 top_brands=?, top_categories=?
                 WHERE id=?""",
              (purchase_count, total_revenue, conv_rate, roi, budget, branch,
               new_customers, existing_customers,
               json.dumps(top_brands), json.dumps(top_cats), camp_id))
    conn.commit()
    print(f"  Successfully saved to database!")

def main():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    row67 = c.execute("SELECT id FROM campaigns WHERE sl_no=67").fetchone()
    row37 = c.execute("SELECT id FROM campaigns WHERE sl_no=37").fetchone()

    if row67:
        process_campaign(c, conn, row67['id'])
    if row37:
        process_campaign(c, conn, row37['id'])

    conn.close()

if __name__ == '__main__':
    main()
