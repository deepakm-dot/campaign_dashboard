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
