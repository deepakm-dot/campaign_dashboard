import sqlite3

try:
    conn = sqlite3.connect('campaigns.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    print("Tables:", [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
    for r in c.execute("SELECT * FROM campaigns WHERE campaign_name LIKE '%kerala%'").fetchall():
        print(dict(r))
except Exception as e:
    print("Error:", e)
