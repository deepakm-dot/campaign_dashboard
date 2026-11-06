"""
Consumer Electronics (CE) Cross-Sell Cohort Tracker.

Tracks the 5,44,635 Excel cohort (5,44,634 unique Mobile / Laptop / Both buyers from
01 Nov 2025 to 31 Oct 2026 who had 0 prior Consumer Electronics purchases) on a daily basis
against ClickHouse POS sales (`azure_sales_report`, `azure_invoice_report`, `item_master`).

STRICTLY READ-ONLY on ClickHouse (`ch_db.query` with `readonly=1`).
Includes all 25 products under `im.category = 'CONSUMER ELECTRONICS'`.
Supports filtering by RBM, BDM, Store, Segment, CE Product, and Date Range,
and reports Target Cohort, Converted Buyers, Conversion %, Units Sold, and Revenue Generated.
"""

import os
import io
import csv
import gzip
import json
import time
import threading
from datetime import datetime
from collections import Counter, defaultdict

import ch_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

DEFAULT_EXCEL_PATH = os.path.join(ROOT_DIR, 'reports', 'mobile lap no CE Nov 2025 to oct 31 2026.xlsx')
FALLBACK_DOWNLOADS_EXCEL = r'c:\Users\deepak.m_myg\Downloads\mobile lap no CE Nov 2025 to oct 31 2026.xlsx'
CACHE_GZ_PATH = os.path.join(DATA_DIR, 'ce_cohort_customers.csv.gz')
CACHE_META_PATH = os.path.join(DATA_DIR, 'ce_cohort_meta.json')
RECOVERED_NOV1_3_PATH = os.path.join(DATA_DIR, 'ce_nov1_3_recovered_customers.json')

# All 25 verified products under im.category = 'CONSUMER ELECTRONICS' in item_master
ALL_25_CE_PRODUCTS = [
    {'product': 'CROCKERY',         'skus': 6481, 'description': 'Cookware, Glassware, Chopper, Pressure Cooker, Kadai, Water Bottle'},
    {'product': 'SMALL APPLIANCES', 'skus': 3356, 'description': 'Mixer Grinder, Ceiling/Pedestal/Wall/Table Fan, Iron Box, Kettle, Induction, Air Fryer, Gas Stove'},
    {'product': 'REFRIGERATORS',    'skus': 2427, 'description': 'Direct Cool (DC), Frost Free (FF), Side-by-Side (SBS), Visi Cooler'},
    {'product': 'TV',               'skus': 2065, 'description': 'LED, QLED, OLED, Smart TV, Signage TV'},
    {'product': 'AIR CONDITIONER',  'skus': 1521, 'description': 'Split AC, Inverter AC, Tower AC, AC Indoor'},
    {'product': 'WASHING MACHINES', 'skus': 1391, 'description': 'Front Load (FL), Top Load (TL), Semi-Automatic (SA)'},
    {'product': 'AC OUTDOOR',       'skus': 1150, 'description': 'AC Outdoor Units & Outdoor Stands'},
    {'product': 'HOME APPLIANCES',  'skus': 1099, 'description': 'Water Purifier, Water Heater/Geyser, Air Cooler, Vacuum Cleaner, Inverter, Chimney, Hob'},
    {'product': 'HOUSE HOLD',       'skus': 966,  'description': 'Mattress, Pillow, Cleaning Set, Cloths Dryer Stand, Home Decor'},
    {'product': 'MICROWAVE OVEN',   'skus': 346,  'description': 'Solo, Grill, Convection, OTG, Built-in Oven'},
    {'product': 'STABILIZER',       'skus': 131,  'description': 'AC, TV & Refrigerator Voltage Stabilizers'},
    {'product': 'FREEZER',          'skus': 114,  'description': 'Deep Freezers, Chest Freezers, Built-in Freezers'},
    {'product': 'CEGI',             'skus': 89,   'description': 'CE Gift & Promotional Items (TV Stand, Extension Box, Dinner Plate, Bed Sheet)'},
    {'product': 'DUMMY',            'skus': 87,   'description': 'Display Dummy Units (AC Indoor, Water Purifier, Dryer)'},
    {'product': 'HA ACCESSORIES',   'skus': 82,   'description': 'WM/Ref Stands, AC Wall Brackets, Installation Kits, WM Covers'},
    {'product': 'DISH WASHER',      'skus': 66,   'description': 'Free-standing & Built-in Dishwashers'},
    {'product': 'DRIER-DW-FREEZER', 'skus': 34,   'description': 'Combined Dryer / Dishwasher / Freezer SKU Group'},
    {'product': 'DETERGENT',        'skus': 28,   'description': 'Dishwasher & Washing Machine Detergents / Liquids'},
    {'product': 'DRYER',            'skus': 17,   'description': 'Clothes Dryers'},
    {'product': 'DEMO HA',          'skus': 13,   'description': 'Demo Home Appliance Units'},
    {'product': 'RECHARGE',         'skus': 10,   'description': 'Recharge / Non-GST Recharge'},
    {'product': 'GENERALS',         'skus': 6,    'description': 'General CE / Water Purifier Items'},
    {'product': 'SIM',              'skus': 4,    'description': 'SIM / SIM Adapter / SIM Tray'},
    {'product': 'DTH',              'skus': 2,    'description': 'DTH Connections'},
    {'product': 'WATER PURIFIER',   'skus': 1,    'description': 'Dedicated Water Purifier SKU (WTH00022; primary WPU SKUs under HOME APPLIANCES)'},
]

_LOCK = threading.Lock()
_COHORT_MEM = {
    'loaded': False,
    'meta': {},
    # mobile -> tuple(rbm, bdm, customer_name, slab, available_points, store_name, segment, brand, last_purchase_date)
    'by_mobile': {},
    'recovered_nov1_3': {},
    # Pre-indexed filter hierarchy and cohort counts
    'rbm_bdms': {},       # rbm -> sorted list of bdms
    'rbm_bdm_stores': {}, # (rbm, bdm) -> sorted list of stores
    'all_rbms': [],
    'all_bdms': [],
    'all_stores': [],
    'all_segments': [],
}

_SALES_CACHE = {
    'key': None,
    'ts': 0,
    'rows': [],
    'latest_pos_date': ''
}


def _clean_mobile(val):
    s = str(val or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    digits = ''.join(ch for ch in s if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else ''


def _norm_date(d_str, default=''):
    s = str(d_str or '').strip()[:10]
    if not s:
        return default
    parts = s.replace('/', '-').split('-')
    if len(parts) == 3 and len(parts[0]) == 2 and len(parts[2]) == 4:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s


def build_cache_from_excel(excel_path=None):
    """Parse the Excel cohort file and write compressed CSV + metadata JSON."""
    path = excel_path
    if not path or not os.path.exists(path):
        if os.path.exists(DEFAULT_EXCEL_PATH):
            path = DEFAULT_EXCEL_PATH
        elif os.path.exists(FALLBACK_DOWNLOADS_EXCEL):
            path = FALLBACK_DOWNLOADS_EXCEL
        elif os.path.exists(CACHE_GZ_PATH):
            _SALES_CACHE['ts'] = 0
            if os.path.exists(CACHE_META_PATH):
                with open(CACHE_META_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {'status': 'cached'}
        else:
            raise FileNotFoundError(f"Cohort Excel file not found at {DEFAULT_EXCEL_PATH}")
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]

    seg_counts = Counter()
    rbm_counts = Counter()
    slab_counts = Counter()
    brand_counts = Counter()
    total_data_rows = 0
    seen_mobiles = set()

    with gzip.open(CACHE_GZ_PATH, 'wt', newline='', encoding='utf-8') as gz_out:
        writer = csv.writer(gz_out)
        writer.writerow([
            'rbm', 'bdm', 'customer_name', 'customer_mobile', 'slab',
            'available_points', 'store_name', 'segment', 'brand', 'last_purchase_date'
        ])
        for idx, row in enumerate(ws.iter_rows(values_only=True)):
            if idx == 0:
                continue
            if not row or all(x is None for x in row):
                continue
            total_data_rows += 1
            rbm = str(row[0] or 'UNASSIGNED').strip().upper()
            bdm = str(row[1] or 'UNASSIGNED').strip().upper()
            cname = str(row[2] or '').strip()
            mob = _clean_mobile(row[3])
            if not mob:
                continue
            slab = str(row[4] if row[4] is not None else '').strip()
            pts = row[5] if row[5] is not None else 0
            sname = str(row[6] or 'UNASSIGNED').strip().upper()
            seg = str(row[7] or 'Mobile Only').strip()
            brand = str(row[8] or '').strip().upper()
            lpd = str(row[9] or '')[:10].strip()

            seg_counts[seg] += 1
            rbm_counts[rbm] += 1
            slab_counts[slab] += 1
            brand_counts[brand] += 1
            seen_mobiles.add(mob)
            writer.writerow([rbm, bdm, cname, mob, slab, pts, sname, seg, brand, lpd])

    wb.close()

    meta = {
        'source_file': os.path.basename(path),
        'source_path': path,
        'excel_total_rows_with_header': total_data_rows + 1,
        'total_customer_rows': total_data_rows,
        'unique_mobiles_count': len(seen_mobiles),
        'cohort_period': '2025-11-01 to 2026-10-31',
        'segments': dict(seg_counts.most_common()),
        'rbms': dict(rbm_counts.most_common()),
        'slabs': dict(slab_counts.most_common()),
        'top_brands': dict(brand_counts.most_common(20)),
        'ingested_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(CACHE_META_PATH, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)

    with _LOCK:
        _COHORT_MEM['loaded'] = False
    return meta


def ensure_cohort_loaded(force=False):
    """Load the 544,634 customer records into memory from compressed CSV cache (takes ~1.5s)."""
    with _LOCK:
        if _COHORT_MEM['loaded'] and not force:
            return _COHORT_MEM

    if not os.path.exists(CACHE_GZ_PATH) or force:
        build_cache_from_excel()

    meta = {}
    if os.path.exists(CACHE_META_PATH):
        try:
            with open(CACHE_META_PATH, 'r', encoding='utf-8') as f:
                meta = json.load(f)
        except Exception:
            meta = {}

    by_mobile = {}
    rbm_bdms = defaultdict(set)
    rbm_bdm_stores = defaultdict(set)
    all_rbms = set()
    all_bdms = set()
    all_stores = set()
    all_segments = set()

    with gzip.open(CACHE_GZ_PATH, 'rt', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for r in reader:
            if len(r) < 10:
                continue
            rbm = (r[0] or 'UNASSIGNED').strip().upper()
            bdm = (r[1] or 'UNASSIGNED').strip().upper()
            cname = r[2]
            mob = r[3]
            slab = r[4]
            pts = r[5]
            sname = (r[6] or 'UNASSIGNED').strip().upper()
            seg = r[7] or 'Mobile Only'
            brand = r[8]
            lpd = r[9]

            if mob not in by_mobile:
                by_mobile[mob] = (rbm, bdm, cname, slab, pts, sname, seg, brand, lpd)
            all_rbms.add(rbm)
            all_bdms.add(bdm)
            all_stores.add(sname)
            all_segments.add(seg)
            rbm_bdms[rbm].add(bdm)
            rbm_bdm_stores[(rbm, bdm)].add(sname)

    with _LOCK:
        _COHORT_MEM['loaded'] = True
        _COHORT_MEM['meta'] = meta
        _COHORT_MEM['by_mobile'] = by_mobile
        _COHORT_MEM['rbm_bdms'] = {k: sorted(v) for k, v in rbm_bdms.items()}
        _COHORT_MEM['rbm_bdm_stores'] = {f"{k[0]}|||{k[1]}": sorted(v) for k, v in rbm_bdm_stores.items()}
        _COHORT_MEM['all_rbms'] = sorted(all_rbms)
        _COHORT_MEM['all_bdms'] = sorted(all_bdms)
        _COHORT_MEM['all_stores'] = sorted(all_stores)
        _COHORT_MEM['all_segments'] = sorted(all_segments)
        return _COHORT_MEM


def _fetch_ce_sales(start_date='2026-11-01', end_date=''):
    """
    Strictly READ-ONLY ClickHouse query (`ch_db.query` with `readonly=1`) fetching
    all Consumer Electronics (`im.category = 'CONSUMER ELECTRONICS'`) sales transactions
    in the given date window. Caches base 2026-11-01+ rows for 300s and filters by date in memory.
    """
    sd = _norm_date(start_date, '2026-11-01')
    ed = _norm_date(end_date, '')
    base_sd = '2026-11-01' if sd >= '2026-11-01' else sd
    now = time.time()

    if _SALES_CACHE.get('key') == base_sd and (now - _SALES_CACHE.get('ts', 0)) < 300 and _SALES_CACHE.get('rows'):
        base_rows = _SALES_CACHE['rows']
        latest_pos_date = _SALES_CACHE['latest_pos_date']
    else:
        # Check latest POS date in azure_sales_report (read-only)
        latest_rows = ch_db.query("SELECT toString(max(toDate(date))) AS max_d FROM azure_sales_report", timeout=30)
        latest_pos_date = (latest_rows[0].get('max_d') if latest_rows else '') or ''

        date_cond = f"toDate(s.date) >= '{base_sd}'"

        # Include all 25 products under im.category = 'CONSUMER ELECTRONICS'
        # (plus standardized CE item_code prefix fallback if a brand-new SKU is not yet in item_master)
        ce_cat_cond = (
            "(im.category = 'CONSUMER ELECTRONICS' OR "
            "(coalesce(im.item_code, '') = '' AND regexpExtract(s.item_code, '^[A-Z]+', 0) IN "
            "('TV', 'AC', 'REF', 'WSM', 'WM', 'FAN', 'CEG', 'VMC', 'WTH', 'CMY', 'WPU')))"
        )
        prod_expr = (
            "if(coalesce(im.product, '') != '', im.product, "
            "multiIf("
            "regexpExtract(s.item_code, '^[A-Z]+', 0) = 'TV', 'TV', "
            "regexpExtract(s.item_code, '^[A-Z]+', 0) = 'AC' AND abs(toFloat64(s.sold_price)) < 100, 'AC OUTDOOR', "
            "regexpExtract(s.item_code, '^[A-Z]+', 0) = 'AC', 'AIR CONDITIONER', "
            "regexpExtract(s.item_code, '^[A-Z]+', 0) = 'REF', 'REFRIGERATORS', "
            "regexpExtract(s.item_code, '^[A-Z]+', 0) IN ('WSM', 'WM'), 'WASHING MACHINES', "
            "regexpExtract(s.item_code, '^[A-Z]+', 0) = 'FAN', 'SMALL APPLIANCES', "
            "regexpExtract(s.item_code, '^[A-Z]+', 0) = 'CEG', 'CEGI', "
            "regexpExtract(s.item_code, '^[A-Z]+', 0) IN ('VMC', 'WTH', 'CMY', 'WPU'), 'HOME APPLIANCES', "
            "'HOME APPLIANCES'))"
        )
        is_od_expr = f"(({prod_expr}) = 'AC OUTDOOR' OR lower(coalesce(im.item_category, '')) = 'ac outdoor' OR lower(coalesce(im.item_name, '')) LIKE 'o/d%')"
        units_expr = f"if({is_od_expr}, 0, if(s.invoice_no LIKE '%-SR-%', -abs(toInt64(s.qty)), if(toFloat64(s.sold_price) < 0, 0, toInt64(s.qty))))"
        raw_qty_expr = "if(s.invoice_no LIKE '%-SR-%', -abs(toInt64(s.qty)), toInt64(s.qty))"

        sql = f"""
            SELECT
                toString(toDate(s.date)) AS sale_date,
                trim(i.customer_mobile) AS customer_mobile,
                s.invoice_no AS invoice_no,
                s.branch AS branch,
                coalesce(nullIf(trim(bm.branch_name), ''), s.branch) AS purchase_store,
                ({prod_expr}) AS ce_product,
                coalesce(nullIf(trim(im.item_category), ''), ({prod_expr})) AS item_category,
                coalesce(nullIf(trim(im.brand), ''), '-') AS ce_brand,
                coalesce(nullIf(trim(im.item_name), ''), s.item_code) AS item_name,
                sum({units_expr}) AS net_units,
                sum({raw_qty_expr}) AS raw_qty,
                round(sum(toFloat64(s.sold_price) * toInt64(s.qty)), 2) AS revenue
            FROM azure_sales_report s
            INNER JOIN azure_invoice_report i ON i.invoice_no = s.invoice_no
            LEFT JOIN item_master im ON im.item_code = s.item_code
            LEFT JOIN branch_master bm ON bm.code = s.branch
            WHERE {date_cond}
              AND {ce_cat_cond}
              AND length(trim(i.customer_mobile)) >= 10
            GROUP BY sale_date, customer_mobile, invoice_no, branch, purchase_store, ce_product, item_category, ce_brand, item_name
            ORDER BY sale_date DESC, revenue DESC
        """
        base_rows = ch_db.query(sql, timeout=120) or []
        _SALES_CACHE['key'] = base_sd
        _SALES_CACHE['ts'] = now
        _SALES_CACHE['rows'] = base_rows
        _SALES_CACHE['latest_pos_date'] = latest_pos_date

    if sd == base_sd and not ed:
        return base_rows, latest_pos_date

    filtered_rows = [
        r for r in base_rows
        if str(r.get('sale_date') or '') >= sd and (not ed or str(r.get('sale_date') or '') <= ed)
    ]
    return filtered_rows, latest_pos_date


def get_ce_dashboard_data(rbm='all', bdm='all', store='all', segment='all', ce_product='all',
                          start_date='2026-11-01', end_date='', search=''):
    """
    Compute complete CE Cross-Sell dashboard analytics for the selected filters:
    - Filter options (RBMs, cascading BDMs, cascading Stores, Segments, 25 CE Products)
    - Cohort summary KPIs (Target Cohort, Converted Buyers, Conversion %, Units Sold, Revenue Generated, Untapped Base)
    - RBM-wise, BDM-wise, Store-wise, and Segment-wise breakdowns (with Cohort Size, Converted Buyers, Conv %, Units Sold, Revenue)
    - All 25 Consumer Electronics products breakdown
    - Daily conversion trend
    - Converted customer invoice lines
    """
    mem = ensure_cohort_loaded()
    by_mobile = mem['by_mobile']

    f_rbm = (rbm or 'all').strip().upper()
    if f_rbm == 'ALL':
        f_rbm = 'all'
    f_bdm = (bdm or 'all').strip().upper()
    if f_bdm == 'ALL':
        f_bdm = 'all'
    f_store = (store or 'all').strip().upper()
    if f_store == 'ALL':
        f_store = 'all'
    f_seg = (segment or 'all').strip()
    if f_seg.lower() == 'all':
        f_seg = 'all'
    f_prod = (ce_product or 'all').strip().upper()
    if f_prod == 'ALL':
        f_prod = 'all'
    q_search = (search or '').strip().lower()

    # Cascading filter lists based on current RBM & BDM selections
    avail_bdms = mem['all_bdms'] if f_rbm == 'all' else mem['rbm_bdms'].get(f_rbm, [])
    if f_bdm != 'all' and f_bdm not in avail_bdms:
        f_bdm = 'all'

    if f_rbm == 'all' and f_bdm == 'all':
        avail_stores = mem['all_stores']
    elif f_rbm != 'all' and f_bdm == 'all':
        st_set = set()
        for b in avail_bdms:
            st_set.update(mem['rbm_bdm_stores'].get(f"{f_rbm}|||{b}", []))
        avail_stores = sorted(st_set)
    elif f_rbm == 'all' and f_bdm != 'all':
        st_set = set()
        for r_key in mem['all_rbms']:
            st_set.update(mem['rbm_bdm_stores'].get(f"{r_key}|||{f_bdm}", []))
        avail_stores = sorted(st_set)
    else:
        avail_stores = mem['rbm_bdm_stores'].get(f"{f_rbm}|||{f_bdm}", [])

    if f_store != 'all' and f_store not in avail_stores:
        f_store = 'all'

    # 1. Aggregate cohort counts for filtered base + RBM / BDM / Store / Segment tables
    filtered_cohort_count = 0
    filtered_seg_counts = Counter()

    rbm_cohort = defaultdict(lambda: {'cohort': 0, 'mob_only': 0, 'lap_only': 0, 'both': 0})
    bdm_cohort = defaultdict(lambda: {'rbm': '', 'cohort': 0, 'mob_only': 0, 'lap_only': 0, 'both': 0})
    store_cohort = defaultdict(lambda: {'rbm': '', 'bdm': '', 'cohort': 0, 'mob_only': 0, 'lap_only': 0, 'both': 0})

    # Track which mobiles pass the cohort filters (rbm, bdm, store, segment)
    # Optimization: if all == 'all', every mobile in by_mobile passes
    all_cohort_filters_open = (f_rbm == 'all' and f_bdm == 'all' and f_store == 'all' and f_seg == 'all')

    for mob, rec in by_mobile.items():
        c_rbm, c_bdm, c_name, c_slab, c_pts, c_store, c_seg, c_brand, c_lpd = rec

        if not all_cohort_filters_open:
            if f_rbm != 'all' and c_rbm != f_rbm:
                continue
            if f_bdm != 'all' and c_bdm != f_bdm:
                continue
            if f_store != 'all' and c_store != f_store:
                continue
            if f_seg != 'all' and c_seg != f_seg:
                continue

        filtered_cohort_count += 1
        filtered_seg_counts[c_seg] += 1

        r_entry = rbm_cohort[c_rbm]
        r_entry['cohort'] += 1
        if c_seg == 'Mobile Only':
            r_entry['mob_only'] += 1
        elif c_seg == 'Laptop Only':
            r_entry['lap_only'] += 1
        else:
            r_entry['both'] += 1

        b_entry = bdm_cohort[c_bdm]
        b_entry['rbm'] = c_rbm
        b_entry['cohort'] += 1
        if c_seg == 'Mobile Only':
            b_entry['mob_only'] += 1
        elif c_seg == 'Laptop Only':
            b_entry['lap_only'] += 1
        else:
            b_entry['both'] += 1

        s_entry = store_cohort[c_store]
        s_entry['rbm'] = c_rbm
        s_entry['bdm'] = c_bdm
        s_entry['cohort'] += 1
        if c_seg == 'Mobile Only':
            s_entry['mob_only'] += 1
        elif c_seg == 'Laptop Only':
            s_entry['lap_only'] += 1
        else:
            s_entry['both'] += 1

    # 2. Fetch CE POS sales from ClickHouse (read-only) and match against cohort
    ce_sales_rows, latest_pos_date = _fetch_ce_sales(start_date=start_date, end_date=end_date)

    converted_mobiles = set()
    converted_invoices = set()
    total_revenue = 0.0
    total_units = 0

    # Breakdown accumulators for RBM / BDM / Store / Segment / Product / Daily
    rbm_perf = defaultdict(lambda: {'buyers': set(), 'invoices': set(), 'units': 0, 'revenue': 0.0})
    bdm_perf = defaultdict(lambda: {'buyers': set(), 'invoices': set(), 'units': 0, 'revenue': 0.0})
    store_perf = defaultdict(lambda: {'buyers': set(), 'invoices': set(), 'units': 0, 'revenue': 0.0})
    seg_perf = defaultdict(lambda: {'buyers': set(), 'invoices': set(), 'units': 0, 'revenue': 0.0})
    prod_perf = defaultdict(lambda: {'buyers': set(), 'invoices': set(), 'units': 0, 'revenue': 0.0})
    daily_perf = defaultdict(lambda: {'buyers': set(), 'invoices': set(), 'units': 0, 'revenue': 0.0, 'prods': Counter()})

    customer_bills = []

    for r in ce_sales_rows:
        mob = _clean_mobile(r.get('customer_mobile'))
        if not mob:
            continue
        rec = by_mobile.get(mob)
        if not rec:
            continue

        c_rbm, c_bdm, c_name, c_slab, c_pts, c_store, c_seg, c_brand, c_lpd = rec
        if not all_cohort_filters_open:
            if f_rbm != 'all' and c_rbm != f_rbm:
                continue
            if f_bdm != 'all' and c_bdm != f_bdm:
                continue
            if f_store != 'all' and c_store != f_store:
                continue
            if f_seg != 'all' and c_seg != f_seg:
                continue

        prod = str(r.get('ce_product') or '').strip().upper()
        rev = float(r.get('revenue') or 0.0)
        # Use raw_qty if net_units is 0 for products like AC OUTDOOR so unit count is transparent
        u = int(r.get('net_units') or 0)
        raw_u = int(r.get('raw_qty') or 0)
        eff_units = u if prod != 'AC OUTDOOR' else raw_u
        inv = str(r.get('invoice_no') or '')
        s_date = str(r.get('sale_date') or '')

        # Update 25-product breakdown before filtering by single f_prod so user can see all 25 products
        pp = prod_perf[prod]
        pp['buyers'].add(mob)
        pp['invoices'].add(inv)
        pp['units'] += eff_units
        pp['revenue'] += rev

        if f_prod != 'all' and prod != f_prod:
            continue

        rp = rbm_perf[c_rbm]
        rp['buyers'].add(mob)
        rp['invoices'].add(inv)
        rp['units'] += eff_units
        rp['revenue'] += rev

        bp = bdm_perf[c_bdm]
        bp['buyers'].add(mob)
        bp['invoices'].add(inv)
        bp['units'] += eff_units
        bp['revenue'] += rev

        sp = store_perf[c_store]
        sp['buyers'].add(mob)
        sp['invoices'].add(inv)
        sp['units'] += eff_units
        sp['revenue'] += rev

        converted_mobiles.add(mob)
        converted_invoices.add(inv)
        total_revenue += rev
        total_units += eff_units

        sgp = seg_perf[c_seg]
        sgp['buyers'].add(mob)
        sgp['invoices'].add(inv)
        sgp['units'] += eff_units
        sgp['revenue'] += rev

        dp = daily_perf[s_date]
        dp['buyers'].add(mob)
        dp['invoices'].add(inv)
        dp['units'] += eff_units
        dp['revenue'] += rev
        dp['prods'][prod] += eff_units

        bill_item = {
            'sale_date': s_date,
            'invoice_no': inv,
            'customer_mobile': mob,
            'customer_name': c_name,
            'rbm': c_rbm,
            'bdm': c_bdm,
            'cohort_store': c_store,
            'segment': c_seg,
            'slab': c_slab,
            'cohort_brand': c_brand,
            'last_purchase_date': c_lpd,
            'purchase_store': r.get('purchase_store') or r.get('branch') or '',
            'ce_product': prod,
            'item_category': r.get('item_category') or '',
            'ce_brand': r.get('ce_brand') or '',
            'item_name': r.get('item_name') or '',
            'units': eff_units,
            'revenue': round(rev, 2)
        }
        if q_search:
            hay = f"{mob} {c_name} {inv} {c_rbm} {c_bdm} {c_store} {prod} {bill_item['item_name']} {bill_item['ce_brand']} {bill_item['purchase_store']}".lower()
            if q_search not in hay:
                continue
        customer_bills.append(bill_item)

    # 3. Format RBM, BDM, Store, Segment, 25-Product, and Daily tables
    rbm_table = []
    for k, c_info in rbm_cohort.items():
        p_info = rbm_perf[k]
        b_cnt = len(p_info['buyers'])
        c_cnt = c_info['cohort']
        rbm_table.append({
            'name': k,
            'cohort_size': c_cnt,
            'mob_only': c_info['mob_only'],
            'lap_only': c_info['lap_only'],
            'both': c_info['both'],
            'converted_buyers': b_cnt,
            'conversion_rate': round((b_cnt / c_cnt * 100), 3) if c_cnt > 0 else 0.0,
            'invoices': len(p_info['invoices']),
            'units_sold': p_info['units'],
            'revenue': round(p_info['revenue'], 2),
            'untapped': max(0, c_cnt - b_cnt)
        })
    rbm_table.sort(key=lambda x: (x['revenue'], x['units_sold'], x['cohort_size']), reverse=True)

    bdm_table = []
    for k, c_info in bdm_cohort.items():
        p_info = bdm_perf[k]
        b_cnt = len(p_info['buyers'])
        c_cnt = c_info['cohort']
        bdm_table.append({
            'name': k,
            'rbm': c_info['rbm'],
            'cohort_size': c_cnt,
            'mob_only': c_info['mob_only'],
            'lap_only': c_info['lap_only'],
            'both': c_info['both'],
            'converted_buyers': b_cnt,
            'conversion_rate': round((b_cnt / c_cnt * 100), 3) if c_cnt > 0 else 0.0,
            'invoices': len(p_info['invoices']),
            'units_sold': p_info['units'],
            'revenue': round(p_info['revenue'], 2),
            'untapped': max(0, c_cnt - b_cnt)
        })
    bdm_table.sort(key=lambda x: (x['revenue'], x['units_sold'], x['cohort_size']), reverse=True)

    store_table = []
    for k, c_info in store_cohort.items():
        p_info = store_perf[k]
        b_cnt = len(p_info['buyers'])
        c_cnt = c_info['cohort']
        store_table.append({
            'name': k,
            'rbm': c_info['rbm'],
            'bdm': c_info['bdm'],
            'cohort_size': c_cnt,
            'mob_only': c_info['mob_only'],
            'lap_only': c_info['lap_only'],
            'both': c_info['both'],
            'converted_buyers': b_cnt,
            'conversion_rate': round((b_cnt / c_cnt * 100), 3) if c_cnt > 0 else 0.0,
            'invoices': len(p_info['invoices']),
            'units_sold': p_info['units'],
            'revenue': round(p_info['revenue'], 2),
            'untapped': max(0, c_cnt - b_cnt)
        })
    store_table.sort(key=lambda x: (x['revenue'], x['units_sold'], x['cohort_size']), reverse=True)

    products_table = []
    total_all_prod_rev = sum(v['revenue'] for v in prod_perf.values())
    for item in ALL_25_CE_PRODUCTS:
        p_name = item['product']
        p_info = prod_perf[p_name]
        rev = round(p_info['revenue'], 2)
        products_table.append({
            'product': p_name,
            'skus_in_master': item['skus'],
            'description': item['description'],
            'converted_buyers': len(p_info['buyers']),
            'invoices': len(p_info['invoices']),
            'units_sold': p_info['units'],
            'revenue': rev,
            'share_pct': round((rev / total_all_prod_rev * 100), 2) if total_all_prod_rev > 0 else 0.0
        })
    products_table.sort(key=lambda x: (x['revenue'], x['units_sold'], x['skus_in_master']), reverse=True)

    daily_table = []
    for d in sorted(daily_perf.keys(), reverse=True):
        dp = daily_perf[d]
        top_p = dp['prods'].most_common(1)[0][0] if dp['prods'] else '-'
        daily_table.append({
            'date': d,
            'converted_buyers': len(dp['buyers']),
            'invoices': len(dp['invoices']),
            'units_sold': dp['units'],
            'revenue': round(dp['revenue'], 2),
            'top_product': top_p
        })

    conv_count = len(converted_mobiles)
    conv_rate = round((conv_count / filtered_cohort_count * 100), 3) if filtered_cohort_count > 0 else 0.0
    untapped_count = max(0, filtered_cohort_count - conv_count)

    return {
        'status': 'ok',
        'meta': {
            **mem['meta'],
            'latest_pos_date': latest_pos_date,
            'start_date': (start_date or '2026-11-01')[:10],
            'end_date': (end_date or latest_pos_date or '')[:10],
        },
        'filters': {
            'selected': {
                'rbm': f_rbm,
                'bdm': f_bdm,
                'store': f_store,
                'segment': f_seg,
                'ce_product': f_prod,
                'start_date': (start_date or '2026-11-01')[:10],
                'end_date': (end_date or '')[:10],
            },
            'rbms': mem['all_rbms'],
            'bdms': avail_bdms,
            'stores': avail_stores,
            'all_bdms': mem['all_bdms'],
            'all_stores': mem['all_stores'],
            'rbm_bdms': mem['rbm_bdms'],
            'rbm_bdm_stores': mem['rbm_bdm_stores'],
            'segments': mem['all_segments'],
            'ce_products': [x['product'] for x in ALL_25_CE_PRODUCTS]
        },
        'kpis': {
            'total_excel_rows': mem['meta'].get('excel_total_rows_with_header', 544635),
            'cohort_customers': filtered_cohort_count,
            'mobile_only_customers': filtered_seg_counts.get('Mobile Only', 0),
            'laptop_only_customers': filtered_seg_counts.get('Laptop Only', 0),
            'both_customers': filtered_seg_counts.get('Both Mobile & Laptop', 0),
            'converted_buyers': conv_count,
            'conversion_rate_pct': conv_rate,
            'total_invoices': len(converted_invoices),
            'total_units_sold': total_units,
            'total_revenue': round(total_revenue, 2),
            'avg_revenue_per_buyer': round(total_revenue / conv_count, 2) if conv_count > 0 else 0.0,
            'untapped_customers': untapped_count
        },
        'rbm_breakdown': rbm_table,
        'bdm_breakdown': bdm_table,
        'store_breakdown': store_table,
        'products_25_breakdown': products_table,
        'daily_breakdown': daily_table,
        'converted_bills': customer_bills[:500],
        'total_converted_bills': len(customer_bills)
    }


def export_ce_excel_report(rbm='all', bdm='all', store='all', segment='all', ce_product='all',
                           start_date='2026-11-01', end_date=''):
    """Generate a formatted multi-sheet Excel report (.xlsx) for the active CE Cross-Sell filters."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    data = get_ce_dashboard_data(
        rbm=rbm, bdm=bdm, store=store, segment=segment,
        ce_product=ce_product, start_date=start_date, end_date=end_date
    )

    wb = openpyxl.Workbook()
    hdr_fill = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
    hdr_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
    sub_fill = PatternFill(start_color='F1F5F9', end_color='F1F5F9', fill_type='solid')
    bold_font = Font(name='Calibri', size=11, bold=True)
    reg_font = Font(name='Calibri', size=11)
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    def _style_sheet(ws, headers, rows, col_widths=None):
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            c = ws.cell(row=1, column=col_idx)
            c.fill = hdr_fill
            c.font = hdr_font
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            c.border = thin_border
        ws.row_dimensions[1].height = 26

        for r_idx, r_vals in enumerate(rows, start=2):
            ws.append(r_vals)
            for c_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=r_idx, column=c_idx)
                cell.font = reg_font
                cell.border = thin_border
                if isinstance(cell.value, float):
                    cell.number_format = '#,##0.00'
                elif isinstance(cell.value, int):
                    cell.number_format = '#,##0'

        if col_widths:
            for i, w in enumerate(col_widths, start=1):
                ws.column_dimensions[get_column_letter(i)].width = w
        else:
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(max_len + 4, 12), 42)

    # Sheet 1: Summary & RBM Breakdown
    ws1 = wb.active
    ws1.title = 'RBM_Summary'
    _style_sheet(
        ws1,
        ['RBM', 'Cohort Customers', 'Conversion %', 'Converted Buyers', 'CE Revenue Generated (₹)', 'Untapped Base'],
        [[r['name'], r['cohort_size'], r['conversion_rate'], r['converted_buyers'], r['revenue'], r['untapped']]
         for r in data['rbm_breakdown']]
    )

    # Sheet 2: BDM Breakdown
    ws2 = wb.create_sheet('BDM_Wise')
    _style_sheet(
        ws2,
        ['BDM', 'RBM', 'Cohort Customers', 'Conversion %', 'Converted Buyers', 'CE Revenue Generated (₹)', 'Untapped Base'],
        [[r['name'], r['rbm'], r['cohort_size'], r['conversion_rate'], r['converted_buyers'], r['revenue'], r['untapped']]
         for r in data['bdm_breakdown']]
    )

    # Sheet 3: Store Breakdown
    ws3 = wb.create_sheet('Store_Wise')
    _style_sheet(
        ws3,
        ['Store Name', 'RBM', 'BDM', 'Cohort Customers', 'Conversion %', 'Converted Buyers', 'CE Revenue Generated (₹)', 'Untapped Base'],
        [[r['name'], r['rbm'], r['bdm'], r['cohort_size'], r['conversion_rate'], r['converted_buyers'], r['revenue'], r['untapped']]
         for r in data['store_breakdown']]
    )

    # Sheet 4: All 25 CE Products
    ws4 = wb.create_sheet('25_CE_Products')
    _style_sheet(
        ws4,
        ['#', 'CE Product (CONSUMER ELECTRONICS)', 'SKUs in Item Master', 'Converted Buyers',
         'CE Invoices', 'Units Sold', 'Revenue Generated (₹)', 'Revenue Share %', 'Items Included'],
        [[idx, r['product'], r['skus_in_master'], r['converted_buyers'], r['invoices'],
          r['units_sold'], r['revenue'], r['share_pct'], r['description']]
         for idx, r in enumerate(data['products_25_breakdown'], start=1)]
    )

    # Sheet 5: Converted Customer Bills
    ws5 = wb.create_sheet('Converted_Customer_Bills')
    _style_sheet(
        ws5,
        ['Sale Date', 'Invoice No', 'Customer Mobile', 'Customer Name', 'RBM', 'BDM',
         'Cohort Store', 'Segment', 'Purchase Store', 'CE Product', 'Item Category',
         'Brand', 'Item Name', 'Units Sold', 'Revenue Generated (₹)'],
        [[r['sale_date'], r['invoice_no'], r['customer_mobile'], r['customer_name'], r['rbm'], r['bdm'],
          r['cohort_store'], r['segment'], r['purchase_store'], r['ce_product'], r['item_category'],
          r['ce_brand'], r['item_name'], r['units'], r['revenue']]
         for r in data['converted_bills']]
    )

    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio.read()

