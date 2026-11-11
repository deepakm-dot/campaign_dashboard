"""
Consumer Electronics (CE) Upselling Cohort Analytics.

STRICTLY READ-ONLY on ClickHouse (`ch_db.query` with `readonly=1`).

KPI Card 1 — Television Upsell Cohort:
- Unique 10-digit customer mobile numbers who purchased a 32-inch Television (any brand,
  excluding spare/replacement panels) on or before 01 November 2024 (`2024-11-01`),
  AND have NOT purchased any Television after `2024-11-01`.
"""

import time
import threading
import ch_db

_LOCK = threading.Lock()
_UPSELL_CACHE = {
    'ts': 0,
    'data': None,
}
CACHE_TTL_SECONDS = 300


def invalidate_upsell_cache():
    """Clear cached CE Upselling metrics so the next request queries ClickHouse fresh."""
    with _LOCK:
        _UPSELL_CACHE['ts'] = 0
        _UPSELL_CACHE['data'] = None


def get_ce_upselling_data(force=False):
    """
    Compute CE Upselling KPIs from ClickHouse POS warehouse tables (`readonly=1`).
    """
    now = time.time()
    with _LOCK:
        if not force and _UPSELL_CACHE['data'] is not None and (now - _UPSELL_CACHE['ts']) < CACHE_TTL_SECONDS:
            return _UPSELL_CACHE['data']

    # 1. Fetch latest POS date (strictly read-only via ch_db.query -> readonly=1)
    latest_rows = ch_db.query(
        "SELECT toString(max(toDate(date))) AS max_d FROM azure_sales_report",
        timeout=30
    )
    latest_pos_date = (latest_rows[0].get('max_d') if latest_rows else '') or ''

    # 2. KPI Card 1: Television (32-inch TV bought on or before 2024-11-01, and NO TV bought after 2024-11-01)
    #    - Filters strictly to retail Television units (`upper(trim(im.product)) = 'TV'`, excluding spare LCD panels)
    #    - Matches 32-inch TVs via `im.item_group` ('32', '<BRAND> 32', etc.) with 0 false positives
    #    - Uses net quantity > 0 on/before 2024-11-01 so full same-period credit-note returns are excluded,
    #      and net quantity <= 0 after 2024-11-01 to confirm no subsequent TV purchase was kept.
    tv_sql = """
        WITH tv_cust AS (
            SELECT
                right(replaceRegexpAll(replaceRegexpOne(trim(i.customer_mobile), '\\\\.0+$', ''), '[^0-9]', ''), 10) AS mob,
                sumIf(
                    toInt64(s.qty),
                    toDate(s.date) <= '2024-11-01'
                    AND upper(im.item_group) NOT LIKE '%PANAL%'
                    AND upper(im.item_name) NOT LIKE '%PANAL%'
                    AND upper(im.item_name) NOT LIKE '%PANEL%'
                    AND (
                        trim(im.item_group) = '32'
                        OR match(upper(im.item_group), '(^|[^0-9])32([^0-9]|$)')
                    )
                ) AS net_32_on_or_before,
                sumIf(
                    toInt64(s.qty),
                    toDate(s.date) > '2024-11-01'
                    AND upper(im.item_group) NOT LIKE '%PANAL%'
                    AND upper(im.item_name) NOT LIKE '%PANAL%'
                    AND upper(im.item_name) NOT LIKE '%PANEL%'
                ) AS net_any_tv_after
            FROM azure_sales_report s
            INNER JOIN azure_invoice_report i ON i.invoice_no = s.invoice_no
            INNER JOIN item_master im ON im.item_code = s.item_code
            WHERE upper(trim(im.product)) = 'TV'
              AND length(replaceRegexpAll(replaceRegexpOne(trim(i.customer_mobile), '\\\\.0+$', ''), '[^0-9]', '')) >= 10
            GROUP BY mob
        )
        SELECT
            countIf(net_32_on_or_before > 0 AND net_any_tv_after <= 0) AS eligible_customers,
            countIf(net_32_on_or_before > 0) AS total_32_buyers_on_or_before,
            countIf(net_32_on_or_before > 0 AND net_any_tv_after > 0) AS bought_tv_after
        FROM tv_cust
        WHERE length(mob) = 10
          AND mob NOT IN ('0000000000', '9999999999', '1111111111', '1234567890')
    """
    tv_rows = ch_db.query(tv_sql, timeout=120)
    tv_row = tv_rows[0] if tv_rows else {}

    result = {
        'status': 'ok',
        'meta': {
            'latest_pos_date': latest_pos_date,
            'tv_cutoff_date': '2024-11-01',
        },
        'kpis': {
            'tv_upsell': {
                'eligible_customers': int(tv_row.get('eligible_customers') or 0),
                'total_32_buyers_on_or_before': int(tv_row.get('total_32_buyers_on_or_before') or 0),
                'bought_tv_after': int(tv_row.get('bought_tv_after') or 0),
                'cutoff_date': '2024-11-01',
            },
            'card_2': None,
            'card_3': None,
        }
    }

    with _LOCK:
        _UPSELL_CACHE['ts'] = time.time()
        _UPSELL_CACHE['data'] = result

    return result
