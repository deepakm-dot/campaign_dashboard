"""
Migrate ALL data from the local SQLite databases into NEW ClickHouse tables.

Source databases
  root    -> <project>/campaign_dashboard.db            (used by the dashboard)
  backend -> <project>/backend/campaign_dashboard.db    (older local copy)

New ClickHouse tables (created by this script; aborts if any already exists)
  campaign_dashboard_campaigns
  campaign_dashboard_campaign_customers
  campaign_dashboard_billing
  campaign_dashboard_config

Every row carries a `source_db` column ('root' / 'backend') because the integer ids
overlap between the two databases. Nothing existing in ClickHouse is read-modified.
The local SQLite files are only read (via a consistent snapshot) and never changed.
"""
import os, sys, csv, json, time, shutil, sqlite3, subprocess, tempfile, urllib.parse

sys.stdout.reconfigure(line_buffering=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)

CH_URL = os.environ.get('CH_URL', 'https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/')
CH_USER = os.environ.get('CH_USER', 'default')
CH_PASS = os.environ.get('CH_PASS', 'ZFlujj9SA_Iei')

SOURCES = {
    'root': os.path.join(ROOT_DIR, 'campaign_dashboard.db'),
    'backend': os.path.join(BASE_DIR, 'campaign_dashboard.db'),
}
T_CAMP = 'campaign_dashboard_campaigns'
T_CUST = 'campaign_dashboard_campaign_customers'
T_BILL = 'campaign_dashboard_billing'
T_CONF = 'campaign_dashboard_config'
ALL_TABLES = [T_CAMP, T_CUST, T_BILL, T_CONF]
CHUNK = 500_000          # < 1,048,576 so each HTTP insert is a single atomic block


def ch(sql, data_path=None, retries=5):
    """Run a statement on ClickHouse over HTTPS using curl.exe (Python's ssl is flaky here)."""
    for attempt in range(1, retries + 1):
        if data_path:
            url = CH_URL + '?' + urllib.parse.urlencode({'query': sql})
            cmd = ['curl.exe', '-s', '-S', '--max-time', '900', '-u', f'{CH_USER}:{CH_PASS}',
                   '-w', '\n%{http_code}', '--data-binary', '@' + data_path, url]
        else:
            cmd = ['curl.exe', '-s', '-S', '--max-time', '300', '-u', f'{CH_USER}:{CH_PASS}',
                   '-w', '\n%{http_code}', '-d', sql, CH_URL]
        r = subprocess.run(cmd, capture_output=True, text=True)
        body, _, code = r.stdout.rpartition('\n')
        if code.strip() == '200':
            return body
        print(f'   ClickHouse attempt {attempt}/{retries} failed: HTTP {code.strip() or "?"} {body[:300]} {r.stderr[:200]}')
        time.sleep(3 * attempt)
    raise RuntimeError('ClickHouse request failed: ' + sql[:120])


def ch_json(sql):
    return json.loads(ch(sql + ' FORMAT JSON')).get('data', [])


def snapshot(src_path, dst_path):
    """Consistent copy using SQLite's backup API (safe even while the server is writing)."""
    src = sqlite3.connect(src_path, timeout=60)
    dst = sqlite3.connect(dst_path)
    with dst:
        src.backup(dst)
    src.close()
    return dst


def cols_of(conn, table):
    return [r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()]


def s(v):
    return '' if v is None else str(v)


def i(v):
    try:
        return int(float(v))
    except Exception:
        return 0


def f(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def write_csv(rows, path):
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        csv.writer(fh, quoting=csv.QUOTE_NONNUMERIC).writerows(rows)


# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------
DDL = {
    T_CAMP: f"""
CREATE TABLE {T_CAMP} (
    source_db LowCardinality(String),
    id Int64, campaign_name String, type String, start_date String, end_date String,
    target_size Int64, purchase_count Int64, purchase_value Float64, conversion_rate Float64,
    roi Float64, budget Float64, source String, campaign_group String, data_source String,
    top_brands String, top_categories String, branch_code String,
    new_customers Int64, existing_customers Int64, sl_no Int64, sheet_tab String,
    migrated_at DateTime DEFAULT now()
) ENGINE = MergeTree ORDER BY (source_db, id)""",
    T_CUST: f"""
CREATE TABLE {T_CUST} (
    source_db LowCardinality(String),
    id Int64, campaign_id Int64, customer_mobile String, customer_name String, store_name String,
    migrated_at DateTime DEFAULT now()
) ENGINE = MergeTree ORDER BY (source_db, campaign_id, customer_mobile, id)""",
    T_BILL: f"""
CREATE TABLE {T_BILL} (
    source_db LowCardinality(String),
    id Int64, bill_date String, bill_no String, customer_mobile String, customer_name String,
    store_name String, item_name String, item_category String, quantity Int64,
    taxable_value Float64, tax_value Float64, net_value Float64, cashier String, sales_person String,
    migrated_at DateTime DEFAULT now()
) ENGINE = MergeTree ORDER BY (source_db, id)""",
    T_CONF: f"""
CREATE TABLE {T_CONF} (
    source_db LowCardinality(String),
    key String, value String,
    migrated_at DateTime DEFAULT now()
) ENGINE = MergeTree ORDER BY (source_db, key)""",
}

CAMP_COLS = [('id', i), ('campaign_name', s), ('type', s), ('start_date', s), ('end_date', s),
             ('target_size', i), ('purchase_count', i), ('purchase_value', f), ('conversion_rate', f),
             ('roi', f), ('budget', f), ('source', s), ('campaign_group', s), ('data_source', s),
             ('top_brands', s), ('top_categories', s), ('branch_code', s),
             ('new_customers', i), ('existing_customers', i), ('sl_no', i), ('sheet_tab', s)]
BILL_COLS = [('id', i), ('bill_date', s), ('bill_no', s), ('customer_mobile', s), ('customer_name', s),
             ('store_name', s), ('item_name', s), ('item_category', s), ('quantity', i),
             ('taxable_value', f), ('tax_value', f), ('net_value', f), ('cashier', s), ('sales_person', s)]


def insert_small(table, src_name, conn, table_cols, work):
    """campaigns / billing / config: small tables, one insert each."""
    have = set(cols_of(conn, table.replace('campaign_dashboard_', '')))
    names = [c for c, _ in table_cols]
    sel = ', '.join(c if c in have else f"NULL AS {c}" for c in names)
    rows = []
    for r in conn.execute(f"SELECT {sel} FROM {table.replace('campaign_dashboard_', '')}"):
        rows.append([src_name] + [fn(v) for (c, fn), v in zip(table_cols, r)])
    if not rows:
        return 0
    path = os.path.join(work, f'{table}_{src_name}.csv')
    write_csv(rows, path)
    cols = ', '.join(['source_db'] + names)
    ch(f'INSERT INTO {table} ({cols}) FORMAT CSV', path)
    os.remove(path)
    return len(rows)


def main():
    print('=== Local -> ClickHouse migration ===')
    # 0. Safety: never touch an existing table
    names = ",".join(f"'{t}'" for t in ALL_TABLES)
    existing = ch_json(f"SELECT name FROM system.tables WHERE database = currentDatabase() AND name IN ({names})")
    if existing:
        print('STOP: these ClickHouse tables already exist, nothing was changed:', [e['name'] for e in existing])
        sys.exit(2)

    work = tempfile.mkdtemp(prefix='ch_migrate_')
    print('Working dir:', work)
    need = sum(os.path.getsize(p) for p in SOURCES.values() if os.path.exists(p)) + 600 * 1024 * 1024
    free = shutil.disk_usage(work).free
    if free < need:
        print(f'STOP: need ~{need//2**20} MB free, only {free//2**20} MB available'); sys.exit(3)

    local_counts = {}
    # 1. Snapshot local DBs (read-only for the originals)
    snaps = {}
    for name, path in SOURCES.items():
        if not os.path.exists(path):
            print(f'Skipping missing DB: {path}'); continue
        t = time.time()
        snap_path = os.path.join(work, f'{name}_snapshot.db')
        snaps[name] = snapshot(path, snap_path)
        print(f'Snapshot of {name} ({os.path.getsize(snap_path)//2**20} MB) in {time.time()-t:.1f}s')

    # 2. Create tables
    for t, ddl in DDL.items():
        ch(ddl)
        print('Created table', t)

    # 3. Copy data
    for name, conn in snaps.items():
        print(f'\n--- Source: {name} ---')
        local_counts[name] = {}
        n = insert_small(T_CAMP, name, conn, CAMP_COLS, work)
        local_counts[name][T_CAMP] = n; print(f'  campaigns: {n} rows')
        n = insert_small(T_BILL, name, conn, BILL_COLS, work)
        local_counts[name][T_BILL] = n; print(f'  billing: {n} rows')
        rows = [[name, s(k), s(v)] for k, v in conn.execute('SELECT key, value FROM config')]
        if rows:
            p = os.path.join(work, 'config.csv'); write_csv(rows, p)
            ch(f'INSERT INTO {T_CONF} (source_db, key, value) FORMAT CSV', p); os.remove(p)
        local_counts[name][T_CONF] = len(rows); print(f'  config: {len(rows)} rows')

        # campaign_customers in id-ordered chunks
        total = conn.execute('SELECT COUNT(*) FROM campaign_customers').fetchone()[0]
        print(f'  campaign_customers: {total:,} rows to copy')
        last_id, done, t0 = -1, 0, time.time()
        path = os.path.join(work, 'cust_chunk.csv')
        while True:
            batch = conn.execute(
                'SELECT id, campaign_id, customer_mobile, customer_name, store_name '
                'FROM campaign_customers WHERE id > ? ORDER BY id LIMIT ?', (last_id, CHUNK)).fetchall()
            if not batch:
                break
            write_csv(([name, int(r[0]), i(r[1]), s(r[2]), s(r[3]), s(r[4])] for r in batch), path)
            ch(f'INSERT INTO {T_CUST} (source_db, id, campaign_id, customer_mobile, customer_name, store_name) FORMAT CSV', path)
            last_id = batch[-1][0]
            done += len(batch)
            rate = done / max(time.time() - t0, 1)
            print(f'    {done:>11,}/{total:,} ({done*100/total:5.1f}%)  {rate:,.0f} rows/s', flush=True)
        if os.path.exists(path):
            os.remove(path)
        local_counts[name][T_CUST] = total

    # 4. Verify
    print('\n=== Verification (local snapshot vs ClickHouse) ===')
    ok = True
    for t in ALL_TABLES:
        rows = ch_json(f'SELECT source_db, count() AS c FROM {t} GROUP BY source_db ORDER BY source_db')
        remote = {r['source_db']: int(r['c']) for r in rows}
        for name in snaps:
            want, got = local_counts[name].get(t, 0), remote.get(name, 0)
            flag = 'OK ' if want == got else 'MISMATCH'
            ok &= (want == got)
            print(f'  {flag} {t:42s} [{name:7s}] local={want:>11,} clickhouse={got:>11,}')
    for name, conn in snaps.items():
        lv = conn.execute('SELECT COALESCE(SUM(purchase_value),0) FROM campaigns').fetchone()[0]
        rv = ch_json(f"SELECT sum(purchase_value) AS v FROM {T_CAMP} WHERE source_db='{name}'")[0]['v']
        print(f'  purchase_value sum [{name}] local={lv:,.2f} clickhouse={float(rv):,.2f}')
        ok &= abs(lv - float(rv)) < 0.01
        lc = conn.execute('SELECT COUNT(DISTINCT customer_mobile) FROM campaign_customers').fetchone()[0]
        rc = ch_json(f"SELECT uniqExact(customer_mobile) AS v FROM {T_CUST} WHERE source_db='{name}'")[0]['v']
        print(f'  distinct mobiles    [{name}] local={lc:,} clickhouse={int(rc):,}')
        ok &= (lc == int(rc))
    print('\nRESULT:', 'ALL DATA MIGRATED AND VERIFIED' if ok else 'CHECK MISMATCHES ABOVE')

    for c in snaps.values():
        c.close()
    shutil.rmtree(work, ignore_errors=True)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
