"""
Store Data vs External Data KPI split for a campaign.

Segmentation of the campaigned audience (campaign_dashboard_campaign_customers):
  * STORE DATA    - the customer bought at least once from ANY store before the campaign start date
  * EXTERNAL DATA - the customer had NO purchase at any store before the campaign start date

KPI logic is identical to the overall campaign KPIs (fixkpi.py), applied per segment:
  * Purchases   = campaigned customers of the segment who purchased in the campaign window (net invoice total > 0)
  * Revenue     = sum of those customers' invoice totals in the campaign window
  * Conversion  = segment purchases / segment audience delivered * 100
  * ROI         = segment revenue / segment cost

The sheet carries ONE delivered count and ONE cost per campaign, so both are shared between the two segments
in proportion to each segment's audience size (equal cost per message). Overall figures are the campaign's own
KPIs (unchanged); the two segments always add up to them for purchases and revenue.

Only read-only SELECTs are run on the POS warehouse (ch_db.query enforces readonly=1). The result is stored as JSON
in the dashboard's own config table under the key  seg_kpi:<campaign_id>.
"""
import json
import time

import ch_db

CONFIG_PREFIX = 'seg_kpi:'
GLOBAL_UNIQUE_KEY = 'global_unique_audience'
_PERIOD_UNIQUE_CACHE = {}
_PERIOD_CACHE_TTL = 300


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _seg_block(audience, purchases, revenue, delivered_total, audience_total, budget):
    share = (audience / audience_total) if audience_total > 0 else 0.0
    delivered = delivered_total * share
    seg_budget = budget * share
    return {
        'audience': int(audience),
        'delivered': round(delivered, 2),
        'purchases': int(purchases),
        'revenue': round(revenue, 2),
        'budget': round(seg_budget, 2),
        'conversion_rate': (purchases / delivered * 100) if delivered > 0 else None,
        'roi': (revenue / seg_budget) if seg_budget > 0 else None,
    }


def compute_segments(camp_id, start_dt, end_dt, branch_cond, delivered_total, budget, overall):
    """Run the segment query and return the dict stored for the campaign.

    branch_cond  - SQL condition on azure_invoice_report.branch ('' for chain-wide), e.g. "branch = 'FLF'"
    overall      - {'purchases','revenue','conversion_rate','roi'} of the whole campaign (kept as is)
    """
    start_dt = str(start_dt)[:10]
    end_dt = str(end_dt or start_dt)[:10]
    branch_filter = f"AND {branch_cond}" if branch_cond else ""
    cust_subq = (f"SELECT customer_mobile FROM {ch_db.T_CUST} "
                 f"WHERE source_db = '{ch_db.SRC}' AND campaign_id = {int(camp_id)}")
    sql = f"""
        SELECT a.is_store AS is_store,
               count() AS audience,
               countIf(p.t > 0) AS purchasers,
               sumIf(p.t, p.t > 0) AS revenue
        FROM (
            SELECT customer_mobile,
                   customer_mobile IN (
                       SELECT DISTINCT customer_mobile FROM ({ch_db.purchase_history_sql(start_dt)})
                   ) AS is_store
            FROM (SELECT DISTINCT customer_mobile FROM {ch_db.T_CUST}
                  WHERE source_db = '{ch_db.SRC}' AND campaign_id = {int(camp_id)})
        ) a
        LEFT JOIN (
            SELECT customer_mobile, SUM(invoice_total) AS t
            FROM azure_invoice_report
            WHERE toDate(date) >= '{start_dt}' AND toDate(date) <= '{end_dt}' {branch_filter}
              AND customer_mobile IN ({cust_subq})
            GROUP BY customer_mobile
            HAVING t > 0
        ) p ON p.customer_mobile = a.customer_mobile
        GROUP BY is_store
    """
    rows = ch_db.query(sql, timeout=180, quote64=True)
    agg = {0: (0, 0, 0.0), 1: (0, 0, 0.0)}
    for r in rows:
        agg[int(r['is_store'])] = (int(_f(r['audience'])), int(_f(r['purchasers'])), _f(r['revenue']))
    aud_total = agg[0][0] + agg[1][0]
    delivered_total = delivered_total if delivered_total and delivered_total > 0 else aud_total
    result = {
        'store': _seg_block(agg[1][0], agg[1][1], agg[1][2], delivered_total, aud_total, budget),
        'external': _seg_block(agg[0][0], agg[0][1], agg[0][2], delivered_total, aud_total, budget),
        'overall': {
            'audience': int(aud_total),
            'delivered': delivered_total,
            'purchases': int(overall.get('purchases') or 0),
            'revenue': round(_f(overall.get('revenue')), 2),
            'budget': budget,
            'conversion_rate': overall.get('conversion_rate'),
            'roi': overall.get('roi'),
        },
        'start': start_dt,
        'computed_at': int(time.time()),
    }
    return result


def save(camp_id, seg):
    ch_db.set_config(f"{CONFIG_PREFIX}{int(camp_id)}", json.dumps(seg))


def load_all():
    """{campaign_id(int): segment dict} for every stored campaign."""
    out = {}
    for k, v in ch_db.get_configs(CONFIG_PREFIX).items():
        try:
            out[int(k[len(CONFIG_PREFIX):])] = json.loads(v)
        except (ValueError, TypeError):
            continue
    return out


def refresh_for_campaign(camp, branch_cond=None, force=False, cache=None):
    """Compute + store the segment split for one campaign dict (as returned by ch_db.list_campaigns).

    Skips the work when a result for the same start date already exists and the campaign's purchases/revenue
    are unchanged (unless force=True). `cache` is an optional {campaign_id: stored dict} from load_all()
    so a loop over many campaigns needs only one config query."""
    cid = int(camp['id'])
    start_dt = (camp.get('start_date') or '')[:10]
    if not start_dt:
        return None
    end_dt = (camp.get('end_date') or start_dt)[:10]
    if branch_cond is None:
        b = (camp.get('branch_code') or '').strip()
        branch_cond = f"branch = '{b}'" if b else ''
    overall = {
        'purchases': camp.get('purchase_count'),
        'revenue': camp.get('purchase_value'),
        'conversion_rate': camp.get('conversion_rate'),
        'roi': camp.get('roi'),
    }
    if not force:
        cur = cache.get(cid) if cache is not None else None
        if cache is None:
            raw = ch_db.get_config(f"{CONFIG_PREFIX}{cid}")
            try:
                cur = json.loads(raw) if raw else None
            except (ValueError, TypeError):
                cur = None
        if cur:
            try:
                o = cur.get('overall', {})
                aud_total = cur['store']['audience'] + cur['external']['audience']
                if (cur.get('start') == start_dt and int(o.get('purchases') or 0) == int(overall['purchases'] or 0)
                        and abs(_f(o.get('revenue')) - _f(overall['revenue'])) < 0.01
                        and _f(o.get('budget')) == _f(camp.get('budget'))
                        and _f(o.get('delivered')) in (_f(camp.get('target_size')), float(aud_total))):
                    return cur
            except Exception:
                pass
    seg = compute_segments(cid, start_dt, end_dt, branch_cond, _f(camp.get('target_size')), _f(camp.get('budget')), overall)
    save(cid, seg)
    if cache is not None:
        cache[cid] = seg
    return seg


def compute_unique_split_for_campaigns(camps):
    """Deduplicated unique customers across `camps`, classified into Store Data vs External Data
    using each customer's earliest campaign start_date and ch_db's dual-table purchase history
    (azure_invoice_report + sales_data, strictly read-only via ch_db.query)."""
    camp_dates = []
    for c in (camps or []):
        cid = int(c.get('id') or 0)
        sd = str(c.get('start_date') or '')[:10]
        if cid > 0 and len(sd) == 10:
            camp_dates.append((cid, sd))
    if not camp_dates:
        return {'unique_customers': 0, 'store_customers': 0, 'external_customers': 0}

    ids_sql = ','.join(str(cid) for cid, _ in camp_dates)
    min_sd = min(sd for _, sd in camp_dates)
    max_sd = max(sd for _, sd in camp_dates)
    case_sql = (
        'multiIf('
        + ', '.join(f"campaign_id = {cid}, toDate('{sd}')" for cid, sd in camp_dates)
        + f", toDate('{min_sd}'))"
    )
    sql = f"""
        WITH uniq_cust AS (
            SELECT customer_mobile, min({case_sql}) AS first_camp_date
            FROM {ch_db.T_CUST}
            WHERE source_db = '{ch_db.SRC}' AND campaign_id IN ({ids_sql})
            GROUP BY customer_mobile
        ),
        hist AS (
            SELECT customer_mobile, min(pdate) AS first_purchase_date
            FROM (
                SELECT customer_mobile, toDate(date) AS pdate
                FROM azure_invoice_report
                WHERE toDate(date) >= '2020-01-01' AND toDate(date) < '{max_sd}'
                  AND customer_mobile != ''
                UNION ALL
                SELECT customer_mobile, parsed_date AS pdate
                FROM sales_data
                WHERE parsed_date >= '2020-01-01' AND parsed_date < '{max_sd}'
                  AND total_value > 0 AND customer_mobile != ''
            )
            GROUP BY customer_mobile
        )
        SELECT
            count() AS unique_customers,
            countIf(h.first_purchase_date > toDate('1970-01-02') AND h.first_purchase_date < u.first_camp_date) AS store_customers
        FROM uniq_cust u
        LEFT JOIN hist h ON u.customer_mobile = h.customer_mobile
    """
    rows = ch_db.query(sql, timeout=180, quote64=True)
    row = rows[0] if rows else {}
    total_u = int(_f(row.get('unique_customers')))
    store_u = int(_f(row.get('store_customers')))
    ext_u = max(0, total_u - store_u)
    return {
        'unique_customers': total_u,
        'store_customers': store_u,
        'external_customers': ext_u,
    }


def refresh_global_unique_split(force=False):
    """Compute and cache All-Time unique / Store Data / External Data customer counts in config."""
    camps = ch_db.list_campaigns(order_by='id')
    cust_counts = ch_db.customer_counts()
    max_sd = max(((c.get('start_date') or '')[:10] for c in camps), default='')
    sig = f"{len(camps)}:{sum(cust_counts.values())}:{max_sd}"

    if not force:
        raw = ch_db.get_config(GLOBAL_UNIQUE_KEY)
        if raw:
            try:
                cur = json.loads(raw)
                if cur.get('sig') == sig and int(cur.get('unique_customers') or 0) > 0:
                    return cur
            except Exception:
                pass

    res = compute_unique_split_for_campaigns(camps)
    res['sig'] = sig
    res['computed_at'] = int(time.time())
    ch_db.set_config(GLOBAL_UNIQUE_KEY, json.dumps(res))
    return res


def get_unique_split_for_period(period_filter_sql=''):
    """Fast lookup for /api/dashboard/stats: uses cached config for All Time, or TTL cache for filtered periods."""
    if not period_filter_sql:
        raw = ch_db.get_config(GLOBAL_UNIQUE_KEY)
        if raw:
            try:
                cur = json.loads(raw)
                if int(cur.get('unique_customers') or 0) > 0:
                    return cur
            except Exception:
                pass
        return refresh_global_unique_split(force=True)

    camps = ch_db.list_campaigns(period_filter_sql, order_by='id')
    if not camps:
        return {'unique_customers': 0, 'store_customers': 0, 'external_customers': 0}

    key = tuple((int(c['id']), (c.get('start_date') or '')[:10]) for c in camps)
    now = time.time()
    cached = _PERIOD_UNIQUE_CACHE.get(key)
    if cached and (now - cached[0]) < _PERIOD_CACHE_TTL:
        return cached[1]

    res = compute_unique_split_for_campaigns(camps)
    _PERIOD_UNIQUE_CACHE[key] = (now, res)
    return res
