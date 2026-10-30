"""
ClickHouse data layer for the Campaign Dashboard.

Replaces the old local SQLite database. All dashboard state now lives in four
ClickHouse tables:

    campaign_dashboard_campaigns
    campaign_dashboard_campaign_customers
    campaign_dashboard_billing
    campaign_dashboard_config

Every row has a `source_db` column. The dashboard reads and writes only the rows
where source_db = SRC ('root'); the 'backend' rows are an archived older copy.

Transport: `curl` is used when available (Python's ssl is flaky against
ClickHouse Cloud on some Windows machines); otherwise urllib is used.
"""
import os
import io
import csv
import json
import time
import shutil
import tempfile
import uuid
import subprocess
import urllib.parse
import urllib.request
import urllib.error
import base64

CH_URL  = os.environ.get('CH_URL',  'https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/')
CH_USER = os.environ.get('CH_USER', 'default')
CH_PASS = os.environ.get('CH_PASS', 'ZFlujj9SA_Iei')

SRC = 'root'   # the source_db partition used by the live dashboard

T_CAMP = 'campaign_dashboard_campaigns'
T_CUST = 'campaign_dashboard_campaign_customers'
T_BILL = 'campaign_dashboard_billing'
T_CONF = 'campaign_dashboard_config'

# Column order of the campaigns table (without source_db / migrated_at)
CAMPAIGN_COLS = [
    'id', 'campaign_name', 'type', 'start_date', 'end_date',
    'target_size', 'purchase_count', 'purchase_value', 'conversion_rate',
    'roi', 'budget', 'source', 'campaign_group', 'data_source',
    'top_brands', 'top_categories', 'branch_code',
    'new_customers', 'existing_customers', 'sl_no', 'sheet_tab',
]
_INT_COLS   = {'id', 'target_size', 'purchase_count', 'new_customers', 'existing_customers', 'sl_no'}
_FLOAT_COLS = {'purchase_value', 'conversion_rate', 'roi', 'budget'}

_CURL = shutil.which('curl.exe') or shutil.which('curl')

LAST_ERROR = None


class ClickHouseError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------
def _post(sql=None, data_path=None, params=None, timeout=300, retries=3):
    """POST a statement. `sql` goes in the body, or in the URL when `data_path` carries the data."""
    global LAST_ERROR
    params = dict(params or {})
    last = ''
    for attempt in range(1, retries + 1):
        try:
            if _CURL:
                if data_path:
                    params['query'] = sql
                    url = CH_URL + '?' + urllib.parse.urlencode(params)
                    cmd = [_CURL, '-s', '-S', '--max-time', str(timeout), '-u', f'{CH_USER}:{CH_PASS}',
                           '-w', '\n%{http_code}', '--data-binary', '@' + data_path, url]
                    r = subprocess.run(cmd, capture_output=True)
                else:
                    url = CH_URL + ('?' + urllib.parse.urlencode(params) if params else '')
                    cmd = [_CURL, '-s', '-S', '--max-time', str(timeout), '-u', f'{CH_USER}:{CH_PASS}',
                           '-w', '\n%{http_code}', '--data-binary', '@-', url]
                    r = subprocess.run(cmd, input=sql.encode('utf-8'), capture_output=True)
                out = r.stdout.decode('utf-8', errors='replace')
                body, _, code = out.rpartition('\n')
                code = code.strip()
                if code == '200':
                    LAST_ERROR = None
                    return body
                last = f'HTTP {code or "?"}: {body[:400]} {r.stderr.decode("utf-8", "replace")[:200]}'
                # A real SQL error (4xx) will not get better on retry
                if code.startswith('4'):
                    break
            else:
                if data_path:
                    params['query'] = sql
                    url = CH_URL + '?' + urllib.parse.urlencode(params)
                    with open(data_path, 'rb') as fh:
                        payload = fh.read()
                else:
                    url = CH_URL + ('?' + urllib.parse.urlencode(params) if params else '')
                    payload = sql.encode('utf-8')
                req = urllib.request.Request(url, data=payload)
                auth = base64.b64encode(f'{CH_USER}:{CH_PASS}'.encode()).decode()
                req.add_header('Authorization', 'Basic ' + auth)
                req.add_header('User-Agent', 'Mozilla/5.0 CampaignDashboard/1.0')
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    LAST_ERROR = None
                    return resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8', 'ignore')
            except Exception:
                body = ''
            last = f'HTTP {e.code}: {body[:400]}'
            if 400 <= e.code < 500:
                break
        except Exception as e:
            last = str(e)
        time.sleep(1.5 * attempt)
    LAST_ERROR = last
    raise ClickHouseError(last)


def query(sql, timeout=120, quote64=False):
    """Run a SELECT and return a list of dicts. 64-bit ints come back as real numbers
    (pass quote64=True for ClickHouse's default of quoting them as strings)."""
    params = {'readonly': 1} if quote64 else {'readonly': 1, 'output_format_json_quote_64bit_integers': 0}
    body = _post(sql + ' FORMAT JSON', params=params, timeout=timeout)
    return json.loads(body).get('data', [])


def execute(sql, timeout=300):
    """Run DDL / ALTER / DELETE and wait for it to complete."""
    return _post(sql, params={'mutations_sync': 2}, timeout=timeout)


def insert_rows(table, columns, rows, chunk=200_000):
    """Bulk insert `rows` (iterable of sequences) into `table` as CSV. Returns row count."""
    total = 0
    buf = []

    def flush():
        nonlocal total, buf
        if not buf:
            return
        fd, path = tempfile.mkstemp(suffix='.csv')
        try:
            with os.fdopen(fd, 'w', newline='', encoding='utf-8') as fh:
                csv.writer(fh, quoting=csv.QUOTE_NONNUMERIC).writerows(buf)
            # ClickHouse silently drops an insert whose content is identical to an earlier one (block dedup),
            # which would lose e.g. a config value that is set back to an earlier value. A unique token per
            # chunk keeps dedup only for retries of the SAME chunk.
            _post(f"INSERT INTO {table} ({', '.join(columns)}) FORMAT CSV", data_path=path, timeout=900,
                  params={'insert_deduplication_token': uuid.uuid4().hex})
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        total += len(buf)
        buf = []

    for r in rows:
        buf.append(r)
        if len(buf) >= chunk:
            flush()
    flush()
    return total


def lit(v):
    """Render a Python value as a ClickHouse SQL literal."""
    if v is None:
        return "''"
    if isinstance(v, bool):
        return '1' if v else '0'
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace('\\', '\\\\').replace("'", "\\'")
    return f"'{s}'"


def _coerce(col, v):
    if col in _INT_COLS:
        try:
            return int(float(v))
        except Exception:
            return 0
    if col in _FLOAT_COLS:
        try:
            return float(v)
        except Exception:
            return 0.0
    return '' if v is None else str(v)


# --------------------------------------------------------------------------
# Campaigns
# --------------------------------------------------------------------------
_CAMP_SELECT = ', '.join(CAMPAIGN_COLS)


def list_campaigns(extra_where='', order_by=''):
    """All dashboard campaigns (dicts with the same keys the old SQLite table had)."""
    sql = f"SELECT {_CAMP_SELECT} FROM {T_CAMP} WHERE source_db = '{SRC}' {extra_where}"
    if order_by:
        sql += f' ORDER BY {order_by}'
    return query(sql)


def get_campaign(campaign_id):
    try:
        cid = int(campaign_id)
    except (TypeError, ValueError):
        return None
    rows = query(f"SELECT {_CAMP_SELECT} FROM {T_CAMP} WHERE source_db = '{SRC}' AND id = {cid} LIMIT 1")
    return rows[0] if rows else None


def next_campaign_id():
    r = query(f"SELECT max(id) AS m FROM {T_CAMP} WHERE source_db = '{SRC}'")
    return int((r[0]['m'] if r else 0) or 0) + 1


def update_campaign(campaign_id, fields):
    """UPDATE the given columns of one campaign (a ClickHouse mutation)."""
    if not fields:
        return
    sets = ', '.join(f'{k} = {lit(_coerce(k, v))}' for k, v in fields.items())
    execute(f"ALTER TABLE {T_CAMP} UPDATE {sets} WHERE source_db = '{SRC}' AND id = {int(campaign_id)}")


def insert_campaign(values):
    """Insert a new campaign and return its generated id."""
    new_id = next_campaign_id()
    row = {c: _coerce(c, values.get(c)) for c in CAMPAIGN_COLS}
    row['id'] = new_id
    for c in ('top_brands', 'top_categories'):
        if not row[c]:
            row[c] = '[]'
    insert_rows(T_CAMP, ['source_db'] + CAMPAIGN_COLS,
                [[SRC] + [row[c] for c in CAMPAIGN_COLS]])
    return new_id


def delete_campaign(campaign_id):
    """Remove a campaign and its customers."""
    cid = int(campaign_id)
    execute(f"DELETE FROM {T_CUST} WHERE source_db = '{SRC}' AND campaign_id = {cid}")
    execute(f"DELETE FROM {T_CAMP} WHERE source_db = '{SRC}' AND id = {cid}")


# --------------------------------------------------------------------------
# Campaign customers
# --------------------------------------------------------------------------
def count_customers(campaign_id):
    r = query(f"SELECT count() AS n FROM {T_CUST} WHERE source_db = '{SRC}' AND campaign_id = {int(campaign_id)}")
    return int(r[0]['n']) if r else 0


def customer_counts():
    """{campaign_id: customer_count} for all campaigns that have customers."""
    r = query(f"SELECT campaign_id, count() AS n FROM {T_CUST} WHERE source_db = '{SRC}' GROUP BY campaign_id")
    return {int(x['campaign_id']): int(x['n']) for x in r}


def delete_customers(campaign_id):
    execute(f"DELETE FROM {T_CUST} WHERE source_db = '{SRC}' AND campaign_id = {int(campaign_id)}")


def next_customer_id():
    r = query(f"SELECT max(id) AS m FROM {T_CUST} WHERE source_db = '{SRC}'")
    return int((r[0]['m'] if r else 0) or 0) + 1


def insert_customers(campaign_id, mobiles, name='', store=''):
    """Bulk-add customers (list of mobiles, or (mobile, name, store) tuples) to a campaign."""
    base = next_customer_id()

    def gen():
        n = base
        for m in mobiles:
            if isinstance(m, (tuple, list)):
                mob, nm, st = (list(m) + ['', ''])[:3]
            else:
                mob, nm, st = m, name, store
            yield [SRC, n, int(campaign_id), mob, nm or '', st or '']
            n += 1

    return insert_rows(T_CUST, ['source_db', 'id', 'campaign_id', 'customer_mobile', 'customer_name', 'store_name'], gen())


def move_customers(from_campaign_id, to_campaign_id):
    """Re-home all customers of one campaign id to another.
    campaign_id is part of the table's sort key, so ALTER UPDATE can't change it: copy, then delete."""
    f, t = int(from_campaign_id), int(to_campaign_id)
    execute(f"INSERT INTO {T_CUST} (source_db, id, campaign_id, customer_mobile, customer_name, store_name) "
            f"SELECT source_db, id, {t}, customer_mobile, customer_name, store_name FROM {T_CUST} "
            f"WHERE source_db = '{SRC}' AND campaign_id = {f}")
    execute(f"DELETE FROM {T_CUST} WHERE source_db = '{SRC}' AND campaign_id = {f}")


def copy_customers(from_campaign_id, to_campaign_id):
    """Copy all customers of one campaign id to another (the source rows are kept)."""
    f, t = int(from_campaign_id), int(to_campaign_id)
    execute(f"INSERT INTO {T_CUST} (source_db, id, campaign_id, customer_mobile, customer_name, store_name) "
            f"SELECT source_db, id, {t}, customer_mobile, customer_name, store_name FROM {T_CUST} "
            f"WHERE source_db = '{SRC}' AND campaign_id = {f}")


def delete_staging():
    """Remove leftovers of an interrupted customer reload (staging rows use a negative campaign_id)."""
    n = query(f"SELECT count() AS n FROM {T_CUST} WHERE source_db = '{SRC}' AND campaign_id < 0")
    if n and int(n[0]['n']) > 0:
        execute(f"DELETE FROM {T_CUST} WHERE source_db = '{SRC}' AND campaign_id < 0")
    return int(n[0]['n']) if n else 0


# --------------------------------------------------------------------------
# Config key/value
# --------------------------------------------------------------------------
def get_config(key, default=None):
    r = query(f"SELECT value FROM {T_CONF} WHERE source_db = '{SRC}' AND key = {lit(key)} LIMIT 1")
    return r[0]['value'] if r else default


def set_config(key, value):
    execute(f"DELETE FROM {T_CONF} WHERE source_db = '{SRC}' AND key = {lit(key)}")
    insert_rows(T_CONF, ['source_db', 'key', 'value'], [[SRC, key, str(value)]])


def get_configs(prefix):
    """{key: value} for every config key starting with `prefix` (one query)."""
    r = query(f"SELECT key, value FROM {T_CONF} WHERE source_db = '{SRC}' AND startsWith(key, {lit(prefix)})")
    return {x['key']: x['value'] for x in r}


def set_configs(values):
    """Set many config keys with one delete + one insert."""
    if not values:
        return
    keys = ', '.join(lit(k) for k in values)
    execute(f"DELETE FROM {T_CONF} WHERE source_db = '{SRC}' AND key IN ({keys})")
    insert_rows(T_CONF, ['source_db', 'key', 'value'], [[SRC, k, str(v)] for k, v in values.items()])
