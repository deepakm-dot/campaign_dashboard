import sqlite3
conn = sqlite3.connect('campaign_dashboard.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Show orphaned campaign_customer IDs
c.execute('SELECT campaign_id, COUNT(*) as cnt FROM campaign_customers GROUP BY campaign_id')
orphan_ids = []
for r in c.fetchall():
    c2 = conn.cursor()
    c2.execute('SELECT id FROM campaigns WHERE id=?', (r['campaign_id'],))
    if not c2.fetchone():
        orphan_ids.append(r['campaign_id'])
        print(f'ORPHAN campaign_id={r["campaign_id"]}, rows={r["cnt"]}')

# Show Paravoor/Vypin current IDs
c.execute("SELECT id, campaign_name, type, start_date, purchase_value FROM campaigns WHERE campaign_name LIKE '%Paravoor%' OR campaign_name LIKE '%Vypin%' ORDER BY id")
print('\nCurrent Paravoor/Vypin campaigns:')
for r in c.fetchall():
    print(dict(r))

# Manual re-link: 587 -> Paravoor WhatsApp (34980 rows), 588 -> Vypin WhatsApp (40604 rows)
# Find the current IDs for these
c.execute("SELECT id, campaign_name, type FROM campaigns WHERE campaign_name LIKE '%Paravoor%' AND type='Whatsapp'")
paravoor_wa = c.fetchone()
c.execute("SELECT id, campaign_name, type FROM campaigns WHERE campaign_name LIKE '%Vypin%' AND type='Whatsapp'")
vypin_wa = c.fetchone()

if paravoor_wa and vypin_wa:
    print(f'\nWill re-link:')
    print(f'  587 -> {paravoor_wa["id"]} ({paravoor_wa["campaign_name"]})')
    print(f'  588 -> {vypin_wa["id"]} ({vypin_wa["campaign_name"]})')
    
    c.execute('UPDATE campaign_customers SET campaign_id=? WHERE campaign_id=?', (paravoor_wa['id'], 587))
    c.execute('UPDATE campaign_customers SET campaign_id=? WHERE campaign_id=?', (vypin_wa['id'], 588))
    conn.commit()
    print('Re-linked successfully!')
    
    # Verify
    c.execute('SELECT campaign_id, COUNT(*) as cnt FROM campaign_customers GROUP BY campaign_id')
    for r in c.fetchall():
        c2 = conn.cursor()
        c2.execute('SELECT campaign_name, type FROM campaigns WHERE id=?', (r['campaign_id'],))
        camp = c2.fetchone()
        status = f"{camp['campaign_name']} / {camp['type']}" if camp else '(ORPHAN)'
        print(f'  campaign_id={r["campaign_id"]} | {status} | {r["cnt"]:,} rows')
else:
    print('Could not find Paravoor/Vypin WhatsApp campaigns!')

conn.close()
