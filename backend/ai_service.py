"""
AI ClickHouse Assistant for Campaign & Sales Intelligence.

Translates natural language questions about sales, products, branches,
and campaigns into optimized ClickHouse queries and returns formatted answers.
Supports both:
1. Built-in deterministic NLP engine (zero external API keys required, instant response).
2. Optional Google Gemini API integration (if GEMINI_API_KEY environment variable is set).
"""

import os
import re
import json
import urllib.request
from datetime import datetime, timedelta

# Import ClickHouse runner from main backend
try:
    from ch_db import query as ch_query
except ImportError:
    import ch_db
    ch_query = ch_db.query

def run_sql(sql):
    try:
        return ch_query(sql, timeout=30, quote64=True)
    except Exception as e:
        print(f"[AI ClickHouse Error] {e}")
        return []

def format_inr(val):
    if val is None:
        return '₹0'
    val = float(val)
    if abs(val) >= 10_000_000:
        return f"₹{val / 10_000_000:.2f}Cr"
    if abs(val) >= 100_000:
        return f"₹{val / 100_000:.2f}L"
    if abs(val) >= 1_000:
        return f"₹{val / 1_000:.2f}K"
    return f"₹{val:,.0f}"

def format_inr_exact(val):
    if val is None:
        return '₹0'
    val = round(float(val))
    s = str(abs(val))
    if len(s) <= 3:
        formatted = s
    else:
        last3 = s[-3:]
        rest = s[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ','.join(groups) + ',' + last3
    prefix = '-₹' if val < 0 else '₹'
    return prefix + formatted

def format_units(val):
    if val is None:
        return '0'
    n = int(round(float(val)))
    return f"{n:,}"

MONTH_MAP = {
    'jan': '01', 'january': '01',
    'feb': '02', 'february': '02',
    'mar': '03', 'march': '03',
    'apr': '04', 'april': '04',
    'may': '05',
    'jun': '06', 'june': '06',
    'jul': '07', 'july': '07',
    'aug': '08', 'august': '08',
    'sep': '09', 'sept': '09', 'september': '09',
    'oct': '10', 'october': '10',
    'nov': '11', 'november': '11',
    'dec': '12', 'december': '12'
}

def extract_dates(text):
    """
    Extracts dates or date ranges from text.
    Returns (start_date, end_date, date_label, is_month)
    """
    t = text.lower()
    
    # 1. Check YYYY-MM-DD
    m_iso = re.findall(r'\b(202[0-9])-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])\b', t)
    if len(m_iso) >= 2:
        d1 = f"{m_iso[0][0]}-{m_iso[0][1]}-{m_iso[0][2]}"
        d2 = f"{m_iso[1][0]}-{m_iso[1][1]}-{m_iso[1][2]}"
        return d1, d2, f"{d1} to {d2}", False
    if len(m_iso) == 1:
        d1 = f"{m_iso[0][0]}-{m_iso[0][1]}-{m_iso[0][2]}"
        return d1, d1, d1, False

    # 2. Check DD-MM-YYYY or DD/MM/YYYY
    m_dmy = re.findall(r'\b(0[1-9]|[12][0-9]|3[01])[-/](0[1-9]|1[0-2])[-/](202[0-9])\b', t)
    if len(m_dmy) >= 2:
        d1 = f"{m_dmy[0][2]}-{m_dmy[0][1]}-{m_dmy[0][0]}"
        d2 = f"{m_dmy[1][2]}-{m_dmy[1][1]}-{m_dmy[1][0]}"
        return d1, d2, f"{d1} to {d2}", False
    if len(m_dmy) == 1:
        d1 = f"{m_dmy[0][2]}-{m_dmy[0][1]}-{m_dmy[0][0]}"
        return d1, d1, d1, False

    # 3. Check "14th August 2026" or "14 August 2026" or "August 14 2026"
    m_word = re.search(r'\b(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+(202[0-9]))?\b', t)
    if m_word:
        day = m_word.group(1).zfill(2)
        month = MONTH_MAP.get(m_word.group(2)[:3], '08')
        year = m_word.group(3) or '2026'
        d = f"{year}-{month}-{day}"
        return d, d, f"{day} {m_word.group(2).capitalize()} {year}", False

    m_word2 = re.search(r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?(?:\s+(202[0-9]))?\b', t)
    if m_word2:
        month = MONTH_MAP.get(m_word2.group(1)[:3], '08')
        day = m_word2.group(2).zfill(2)
        year = m_word2.group(3) or '2026'
        d = f"{year}-{month}-{day}"
        return d, d, f"{day} {m_word2.group(1).capitalize()} {year}", False

    # 4. Check Month Only (e.g., "August 2026", "in August", "in September")
    m_month = re.search(r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s+(202[0-9]))?\b', t)
    if m_month:
        month_name = m_month.group(1)
        month = MONTH_MAP.get(month_name[:3], '08')
        year = m_month.group(2) or '2026'
        # Days in month
        import calendar
        _, last_day = calendar.monthrange(int(year), int(month))
        d1 = f"{year}-{month}-01"
        d2 = f"{year}-{month}-{str(last_day).zfill(2)}"
        return d1, d2, f"{month_name.capitalize()} {year}", True

    return None, None, None, False

# Specific items/appliances matched against item_name
ITEM_SYNONYMS = {
    'PEDESTAL FAN': ['pedestal fan', 'pedestal fans', 'stand fan', 'stand fans'],
    'WALL FAN': ['wall fan', 'wall fans', 'wall mount fan'],
    'TABLE FAN': ['table fan', 'table fans', 'desk fan'],
    'EXHAUST FAN': ['exhaust fan', 'exhaust fans'],
    'CEILING FAN': ['ceiling fan', 'ceiling fans', 'bldc fan', 'bldc ceiling fan'],
    'FAN': ['fan', 'fans'],
    'MIXER': ['mixer', 'grinder', 'mixer grinder', 'mixie', 'juicer'],
    'IRON': ['iron', 'iron box', 'steam iron', 'dry iron'],
    'KETTLE': ['kettle', 'electric kettle'],
    'WATER PURIFIER': ['water purifier', 'purifier', 'ro water', 'water filter'],
    'MICROWAVE': ['microwave', 'microwave oven', 'oven', 'otg', 'convection oven'],
    'INDUCTION': ['induction', 'induction cooker', 'induction cooktop', 'cooktop'],
    'AIR FRYER': ['air fryer', 'airfryer', 'fryer'],
    'GEYSER': ['geyser', 'water heater', 'heater'],
    'SOUNDBAR': ['soundbar', 'sound bar', 'home theatre', 'speaker', 'speakers'],
    'VACUUM': ['vacuum cleaner', 'vacuum', 'cleaner'],
    'TABLET': ['tablet', 'tablets', 'ipad', 'tab'],
    'PRINTER': ['printer', 'printers'],
    'DISH WASHER': ['dishwasher', 'dish washer'],
    'DRYER': ['dryer', 'clothes dryer']
}

PRODUCT_SYNONYMS = {
    'TV': ['tv', 'television', 'televisions', 'led tv', 'smart tv', 'oled', 'qled'],
    'MOBILE': ['mobile', 'mobiles', 'smartphone', 'smartphones', 'phone', 'phones', 'handset'],
    'LAPTOP': ['laptop', 'laptops', 'notebook', 'pc', 'computer'],
    'REFRIGERATORS': ['refrigerator', 'refrigerators', 'fridge', 'fridges', 'deep freezer'],
    'WASHING MACHINES': ['washing machine', 'washing machines', 'washer', 'washers', 'wm'],
    'AIR CONDITIONER': ['ac', 'air conditioner', 'airconditioner', 'air conditioners', 'cooling'],
    'SMART WATCH': ['smart watch', 'smartwatch', 'smart watches', 'wearable watch'],
    'EAR WEARABLES': ['earbuds', 'earphone', 'earphones', 'tws', 'airpods', 'headphone', 'headphones'],
    'AUDIO': ['audio', 'soundbar', 'speaker', 'speakers'],
    'SMALL APPLIANCES': ['small appliance', 'small appliances']
}

def extract_product_and_item(text):
    t = text.lower()
    # 1. First check specific appliance items (longer phrases first, e.g. "ceiling fan" before "fan")
    for item_key, syns in ITEM_SYNONYMS.items():
        for syn in sorted(syns, key=len, reverse=True):
            if re.search(r'\b' + re.escape(syn) + r'\b', t):
                display = syn.title()
                return None, item_key, display
                
    # 2. Check general product categories
    for prod_key, syns in PRODUCT_SYNONYMS.items():
        for syn in sorted(syns, key=len, reverse=True):
            if re.search(r'\b' + re.escape(syn) + r'\b', t):
                display = prod_key.title()
                return prod_key, None, display
                
    return None, None, None

BRANDS = [
    'samsung', 'apple', 'lg', 'sony', 'xiaomi', 'mi', 'redmi', 'vivo', 'oppo',
    'oneplus', 'realme', 'motorola', 'whirlpool', 'haier', 'godrej', 'voltas',
    'lloyd', 'daikin', 'panasonic', 'dell', 'hp', 'lenovo', 'asus', 'acer',
    'boat', 'noise', 'fire-boltt', 'impex', 'philips', 'preethi', 'bajaj',
    'luker', 'v guard', 'v-guard', 'usha', 'atomberg', 'havells', 'crompton',
    'orient', 'morphy richards', 'prestige', 'butterfly', 'sujata'
]

def extract_brand(text):
    t = text.lower()
    for b in BRANDS:
        if re.search(r'\b' + re.escape(b) + r'\b', t):
            if b in ('mi', 'redmi'): return 'XIAOMI'
            if b in ('v-guard', 'v guard'): return 'V GUARD'
            return b.upper()
    return None

def extract_two_dates(text):
    """Return [(iso_date, label), ...] for every specific full date (with year) found, in the order written."""
    t = text.lower()
    found = []  # (position, iso)
    for m in re.finditer(r'\b(202[0-9])-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])\b', t):
        found.append((m.start(), f"{m.group(1)}-{m.group(2)}-{m.group(3)}"))
    for m in re.finditer(r'\b(0?[1-9]|[12][0-9]|3[01])[-/.](0?[1-9]|1[0-2])[-/.](202[0-9])\b', t):
        found.append((m.start(), f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"))
    mon = r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    for m in re.finditer(r'\b(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?\s+' + mon + r'\s+(202[0-9])\b', t):
        found.append((m.start(), f"{m.group(3)}-{MONTH_MAP.get(m.group(2)[:3], '01')}-{m.group(1).zfill(2)}"))
    for m in re.finditer(r'\b' + mon + r'\s+(0?[1-9]|[12][0-9]|3[01])(?:st|nd|rd|th)?,?\s+(202[0-9])\b', t):
        found.append((m.start(), f"{m.group(3)}-{MONTH_MAP.get(m.group(1)[:3], '01')}-{m.group(2).zfill(2)}"))
    found.sort()
    out, seen = [], set()
    for _, iso in found:
        if iso not in seen:
            seen.add(iso)
            out.append(iso)
    return out

def extract_periods(text):
    """Return [(start_iso, end_iso, label), ...] for quarter codes (JFM/AMJ/JAS/OND), Q1-Q4 <year>, and month spans like 'july august september 2026'."""
    import calendar
    t = text.lower()
    found = []
    def add(pos, m1, m2, y, label):
        end = calendar.monthrange(y, m2)[1]
        found.append((pos, f"{y}-{m1:02d}-01", f"{y}-{m2:02d}-{end:02d}", label))
    qcodes = {'jfm': (1, 3), 'amj': (4, 6), 'jas': (7, 9), 'ond': (10, 12)}
    for m in re.finditer(r"\b(jfm|amj|jas|ond)\b\s*(?:'|-)?\s*(20\d\d|\d\d)?\b", t):
        y = m.group(2)
        if not y:
            continue
        y = int(y) if len(y) == 4 else 2000 + int(y)
        a, b = qcodes[m.group(1)]
        add(m.start(), a, b, y, f"{m.group(1).upper()} {y}")
    for m in re.finditer(r'\bq([1-4])\s*(?:of\s+)?(20\d\d)\b', t):
        n, y = int(m.group(1)), int(m.group(2))
        add(m.start(), 3 * n - 2, 3 * n, y, f"Q{n} {y}")
    mon = r'(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)'
    for m in re.finditer(r'\b(' + mon + r'(?:\s*(?:,|-|to|and|&)?\s*' + mon + r')*)\s*,?\s*(20\d\d)\b', t):
        names = re.findall(mon, m.group(1))
        ms = [int(MONTH_MAP.get(n[:3], '01')) for n in names]
        y = int(m.group(2))
        lab = (f"{calendar.month_abbr[ms[0]]} {y}" if len(ms) == 1 else f"{calendar.month_abbr[ms[0]]}-{calendar.month_abbr[ms[-1]]} {y}")
        add(m.start(), min(ms), max(ms), y, lab)
    found.sort()
    out, seen = [], set()
    for _, s, e, lab in found:
        if (s, e) not in seen:
            seen.add((s, e))
            out.append((s, e, lab))
    if len(out) == 1:
        # "JAS 2026 vs previous year" / "... with 2025"
        s, e, lab = out[0]
        y0 = int(s[:4])
        others = [int(y) for y in re.findall(r'\b(20\d\d)\b', t) if int(y) != y0]
        if others:
            y1 = others[-1]
        elif re.search(r'(previous|last|prior)\s+year|same\s+(period|quarter)|yoy|year\s+over\s+year|year-on-year', t):
            y1 = y0 - 1
        else:
            return out
        s1, e1 = f"{y1}{s[4:]}", f"{y1}{e[4:]}"
        if e1[5:] == '02-28' and calendar.isleap(y1):
            e1 = f"{y1}-02-29"
        out.append((s1, e1, lab.replace(str(y0), str(y1))))
    return out[:2]

EXPORT_DIR = os.path.join(__import__('tempfile').gettempdir(), 'ai_exports')

_EXCL_CATS = ("'SCHEME','AC OUTDOOR','D SPARE','SPARE','GDP-SPARE','FIXED ASSETS','DEMO','DEMO ACCESSORIES',"
              "'STATIONERY ITEMS','GIFT ITEMS','OFFER KIT','FOC','SERVICE','SERVICE CHARGES','OSG WARRANTY',"
              "'CARE PLUS','LG AMC','GDOT CARE','TOTAL SECURITY','MOBILE ANTIVIRUS','CEGI','SMART CHOICE'")

PROD_EXPR = ("if(coalesce(im.product,'')='', multiIf(s.item_code LIKE 'MOB%','MOBILE', s.item_code LIKE 'TV%','TV', "
             "s.item_code LIKE 'LAP%','LAPTOP', (s.item_code LIKE 'AC%' AND abs(toFloat64(s.sold_price))>=1000),'AIR CONDITIONER', (s.item_code LIKE 'WSM%' OR s.item_code LIKE 'WM%'),'WASHING MACHINES', "
             "s.item_code LIKE 'REF%','REFRIGERATORS',''), im.product)")

# Only these product categories are considered in quarterly/period comparisons and insights
FOCUS_CATS = ['CROCKERY', 'MOBILE', 'SMALL APPLIANCES', 'ACCESSORIES', 'FRAGRANCE', 'TV', 'WASHING MACHINES',
              'REFRIGERATORS', 'AIR CONDITIONER', 'AUDIO', 'LAPTOP', 'HOUSE HOLD', 'HOME APPLIANCES',
              'PERSONAL CARE', 'HOME THEATRE', 'MICROWAVE OVEN', 'DISH WASHER', 'BT SPEAKERS']
_FOCUS_SQL = ",".join("'" + c + "'" for c in FOCUS_CATS)
# Priority products highlighted first in quarterly comparisons/insights
KEY_CATS = ['MOBILE', 'TV', 'REFRIGERATORS', 'WASHING MACHINES', 'LAPTOP', 'AIR CONDITIONER']

def _pct(new, old):
    return (new - old) / old if old else None

def _fmt_pct(new, old):
    p = _pct(new, old)
    return f"{p * 100:+.1f}%" if p is not None else ("new" if new else "-")

def quarterly_insights(period_a, period_b, branch_code=None, branch_name=None, product=None, lfl=True, direction='both', store_type=None):
    """Store x product-category comparison between two periods (A = base/earlier, B = current/later).
    Like-for-like: only stores that had sales in period A. Returns a chat response dict with an Excel download."""
    import uuid
    d_a, d_a_end, lab_a = period_a
    d_b, d_b_end, lab_b = period_b
    in_a = f"toDate(s.date) BETWEEN '{d_a}' AND '{d_a_end}'"
    in_b = f"toDate(s.date) BETWEEN '{d_b}' AND '{d_b_end}'"
    in_a_plain = in_a.replace('s.date', 'date')
    prod_expr = ("if(coalesce(im.product,'')='', multiIf(s.item_code LIKE 'MOB%','MOBILE', s.item_code LIKE 'TV%','TV', "
                 "s.item_code LIKE 'LAP%','LAPTOP', s.item_code LIKE 'AC%','AIR CONDITIONER', "
                 "s.item_code LIKE 'WM%','WASHING MACHINES', s.item_code LIKE 'REF%','REFRIGERATORS',''), im.product)")
    qty = "if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))"
    rev = "toFloat64(s.sold_price) * toInt64(s.qty)"
    extra = ""
    st_filter = f" AND upper(coalesce(bm.branch_name, s.branch)) LIKE '%{store_type}%'" if store_type else ""
    extra += st_filter
    if branch_code:
        extra += f" AND s.branch = '{branch_code}'"
    if product:
        extra += f" AND {prod_expr} = '{product}'"
    if lfl:
        extra += f" AND s.branch IN (SELECT DISTINCT branch FROM azure_sales_report WHERE {in_a_plain})"
    sql = f"""
        SELECT s.branch AS br, any(bm.branch_name) AS nm, {prod_expr} AS grp,
               sumIf({qty}, {in_a}) AS ua, sumIf({qty}, {in_b}) AS ub,
               sumIf({rev}, {in_a}) AS ra, sumIf({rev}, {in_b}) AS rb
        FROM azure_sales_report s
        LEFT JOIN item_master im ON im.item_code = s.item_code
        LEFT JOIN branch_master bm ON bm.code = s.branch
        WHERE (({in_a}) OR ({in_b})) AND s.branch NOT IN ('SMC','3GH') AND s.item_code NOT LIKE 'SRV%'
          AND {('1=1' if product else prod_expr + ' IN (' + _FOCUS_SQL + ')')} {extra}
        GROUP BY s.branch, grp
    """
    try:
        raw = ch_query(sql, timeout=120, quote64=True) or []
    except Exception as e:
        print(f"[Insights SQL Error] {e}")
        raw = []
    rows = []
    for r in raw:
        ua, ub = int(float(r['ua'])), int(float(r['ub']))
        ra, rb = float(r['ra']), float(r['rb'])
        if ua == 0 and ub == 0 and ra == 0 and rb == 0:
            continue
        rows.append({'br': r['br'], 'nm': (r.get('nm') or r['br']), 'cat': r['grp'], 'ua': ua, 'ub': ub, 'ra': ra, 'rb': rb})
    if not rows:
        return {"answer": f"No sales data found for {lab_a} vs {lab_b} with these filters.", "cards": [], "table": None, "suggestions": []}

    # Newly launched stores excluded (sales in B but none in A)
    new_stores = []
    if lfl and not branch_code:
        try:
            new_stores = ch_query(f"""
                SELECT s.branch AS br, coalesce(any(bm.branch_name), s.branch) AS nm,
                       sum(toFloat64(s.sold_price) * toInt64(s.qty)) AS rev, min(toDate(s.date)) AS first_sale
                FROM azure_sales_report s LEFT JOIN branch_master bm ON bm.code = s.branch
                WHERE {in_b} AND s.branch NOT IN ('SMC','3GH') {st_filter}
                  AND s.branch NOT IN (SELECT DISTINCT branch FROM azure_sales_report WHERE {in_a_plain})
                GROUP BY s.branch ORDER BY rev DESC
            """, timeout=60, quote64=True) or []
        except Exception:
            new_stores = []

    stores, cats = {}, {}
    for x in rows:
        st = stores.setdefault(x['br'], {'br': x['br'], 'nm': x['nm'], 'ua': 0, 'ub': 0, 'ra': 0.0, 'rb': 0.0, 'dec': 0, 'inc': 0})
        st['ua'] += x['ua']; st['ub'] += x['ub']; st['ra'] += x['ra']; st['rb'] += x['rb']
        if x['ub'] < x['ua']: st['dec'] += 1
        elif x['ub'] > x['ua']: st['inc'] += 1
        ct = cats.setdefault(x['cat'], {'cat': x['cat'], 'ua': 0, 'ub': 0, 'ra': 0.0, 'rb': 0.0, 'sdec': 0, 'sinc': 0, 'sa': 0, 'sany': 0})
        ct['ua'] += x['ua']; ct['ub'] += x['ub']; ct['ra'] += x['ra']; ct['rb'] += x['rb']
        if x['ua'] > 0 or x['ub'] > 0: ct['sany'] += 1
        if x['ua'] > 0: ct['sa'] += 1
        if x['ub'] < x['ua']: ct['sdec'] += 1
        elif x['ub'] > x['ua']: ct['sinc'] += 1
    store_list = sorted(stores.values(), key=lambda z: z['ub'] - z['ua'])
    cat_list = sorted(cats.values(), key=lambda z: z['ub'] - z['ua'])
    tot_ua, tot_ub = sum(z['ua'] for z in store_list), sum(z['ub'] for z in store_list)
    tot_ra, tot_rb = sum(z['ra'] for z in store_list), sum(z['rb'] for z in store_list)
    dec_stores = [z for z in store_list if z['ub'] < z['ua']]
    pairs_dec = sorted([x for x in rows if x['ub'] < x['ua']], key=lambda x: x['ub'] - x['ua'])
    inc_stores = sorted([z for z in store_list if z['ub'] > z['ua']], key=lambda z: -(z['ub'] - z['ua']))
    pairs_inc = sorted([x for x in rows if x['ub'] > x['ua']], key=lambda x: -(x['ub'] - x['ua']))
    store_rank = {z['br']: i for i, z in enumerate(store_list)}
    store_rank_up = {z['br']: i for i, z in enumerate(sorted(store_list, key=lambda z: -(z['ub'] - z['ua'])))}
    show_less = direction in ('less', 'both')
    show_more = direction in ('more', 'both')

    # ---- Insight sentences ----
    ins = []
    scope_txt = (branch_name or (f"{store_type.title()} stores" if store_type else 'all stores')) + (f" / {product}" if product else "") + (" (like-for-like)" if lfl else "")
    ins.append(f"{lab_b} vs {lab_a} ({scope_txt}): units {tot_ua:,} -> {tot_ub:,} ({_fmt_pct(tot_ub, tot_ua)}), revenue Rs {tot_ra:,.0f} -> Rs {tot_rb:,.0f} ({_fmt_pct(tot_rb, tot_ra)}).")
    if not product:
        for k in KEY_CATS:
            c = cats.get(k)
            if not c:
                continue
            line = (f"\u2605 {k}: units {c['ua']:,} -> {c['ub']:,} ({c['ub'] - c['ua']:+,}, {_fmt_pct(c['ub'], c['ua'])}), "
                    f"revenue Rs {c['ra']:,.0f} -> Rs {c['rb']:,.0f} ({_fmt_pct(c['rb'], c['ra'])}); "
                    f"grew in {c['sinc']}, fell in {c['sdec']} of {c['sany']} stores.")
            if not branch_code:
                if show_less:
                    dn = sorted([x for x in rows if x['cat'] == k and x['ub'] < x['ua']], key=lambda x: x['ub'] - x['ua'])[:3]
                    if dn: line += " Biggest drops: " + ", ".join(f"{x['nm']} ({x['ua']:,}->{x['ub']:,})" for x in dn) + "."
                if show_more:
                    up = sorted([x for x in rows if x['cat'] == k and x['ub'] > x['ua']], key=lambda x: -(x['ub'] - x['ua']))[:3]
                    if up: line += " Biggest gains: " + ", ".join(f"{x['nm']} ({x['ua']:,}->{x['ub']:,})" for x in up) + "."
            ins.append(line)
    if show_more and not product:
        up_c = sorted([c for c in cat_list if c['ub'] > c['ua']], key=lambda c: -(c['ub'] - c['ua']))
        ins.append("Products that sold MORE (all selected categories, by unit gain): " + "; ".join(f"{c['cat']} {c['ua']:,}->{c['ub']:,} ({c['ub'] - c['ua']:+,}, {_fmt_pct(c['ub'], c['ua'])})" for c in up_c) + ".")
    if show_less and not product:
        dn_c = sorted([c for c in cat_list if c['ub'] < c['ua']], key=lambda c: c['ub'] - c['ua'])
        ins.append("Products that sold LESS (by unit drop): " + ("; ".join(f"{c['cat']} {c['ua']:,}->{c['ub']:,} ({c['ub'] - c['ua']:+,}, {_fmt_pct(c['ub'], c['ua'])})" for c in dn_c) or "none") + ".")
    if show_more:
        if not branch_code:
            ins.append(f"{len(inc_stores)} of {len(store_list)} stores sold more units in {lab_b} than in {lab_a}.")
            for z in inc_stores[:5]:
                best = sorted([x for x in rows if x['br'] == z['br'] and x['ub'] > x['ua']], key=lambda x: -(x['ub'] - x['ua']))[:3]
                btxt = ", ".join(f"{w['cat']} ({w['ua']:,}->{w['ub']:,})" for w in best)
                if product:
                    ins.append(f"{product} grew most at {z['nm']}: {z['ua']:,}->{z['ub']:,} ({z['ub'] - z['ua']:+,}).")
                else:
                    ins.append(f"Biggest unit gain: {z['nm']} {z['ua']:,}->{z['ub']:,} ({z['ub'] - z['ua']:+,}); main drivers: {btxt}.")
        elif pairs_inc:
            z = store_list[0] if len(store_list) == 1 else sorted(store_list, key=lambda z: -(z['ub'] - z['ua']))[0]
            ins.append(f"{z['nm']}: {z['inc']} product categories grew. Biggest gains: " + ", ".join(f"{w['cat']} ({w['ua']:,}->{w['ub']:,})" for w in pairs_inc[:8]) + ".")
        growers = sorted([c for c in cat_list if c['sinc'] > 0 and c['ub'] > c['ua']], key=lambda c: -c['sinc'])[:6]
        if growers and not branch_code:
            ins.append("Growth spread across many stores: " + "; ".join(f"{c['cat']} grew in {c['sinc']} of {c['sany']} stores (total {c['ua']:,}->{c['ub']:,}, {_fmt_pct(c['ub'], c['ua'])})" for c in growers) + ".")
        multi_up = sorted(inc_stores, key=lambda z: -z['inc'])[:3]
        if multi_up and not branch_code and not product:
            ins.append("Stores with most growing categories: " + "; ".join(f"{z['nm']} ({z['inc']} categories)" for z in multi_up) + ".")
        rev_up_units_down = [z for z in store_list if z['rb'] > z['ra'] and z['ub'] <= z['ua']]
        if rev_up_units_down and not branch_code:
            ins.append(f"{len(rev_up_units_down)} stores sold fewer/equal units but earned more revenue (mix shifted to higher-value products).")
    if show_less and not branch_code:
        ins.append(f"{len(dec_stores)} of {len(store_list)} stores sold fewer units in {lab_b} than in {lab_a}.")
        for z in store_list[:5]:
            if z['ub'] >= z['ua']: break
            worst = sorted([x for x in rows if x['br'] == z['br'] and x['ub'] < x['ua']], key=lambda x: x['ub'] - x['ua'])[:3]
            wtxt = ", ".join(f"{w['cat']} ({w['ua']:,}->{w['ub']:,})" for w in worst)
            if product:
                ins.append(f"{product} dropped most at {z['nm']}: {z['ua']:,}->{z['ub']:,} ({z['ub'] - z['ua']:+,}).")
            else:
                ins.append(f"Biggest unit drop: {z['nm']} {z['ua']:,}->{z['ub']:,} ({z['ub'] - z['ua']:+,}); main drags: {wtxt}.")
    elif show_less:
        z = store_list[0]
        worst = pairs_dec[:8]
        if worst:
            ins.append(f"{z['nm']}: {z['dec']} product categories declined. Biggest drops: " + ", ".join(f"{w['cat']} ({w['ua']:,}->{w['ub']:,})" for w in worst) + ".")
    broad = sorted([c for c in cat_list if c['sdec'] > 0 and c['ub'] < c['ua']], key=lambda c: -c['sdec'])[:5]
    if show_less and broad and not branch_code:
        ins.append("Declines spread across many stores: " + "; ".join(f"{c['cat']} fell in {c['sdec']} of {c['sany']} stores (total {c['ua']:,}->{c['ub']:,})" for c in broad) + ".")
    multi = sorted(dec_stores, key=lambda z: -z['dec'])[:3]
    if show_less and multi and not branch_code and not product:
        ins.append("Stores with most declining categories: " + "; ".join(f"{z['nm']} ({z['dec']} categories)" for z in multi) + ".")
    rev_down_units_up = [z for z in store_list if z['rb'] < z['ra'] and z['ub'] >= z['ua']]
    if show_less and rev_down_units_up and not branch_code:
        ins.append(f"{len(rev_down_units_up)} stores kept/raised units but earned less revenue (mix shifted to cheaper products).")
    inactive = [z for z in store_list if z['ub'] == 0 and z['ua'] > 0]
    if show_less and inactive and not branch_code:
        ins.append(f"{len(inactive)} stores had sales in {lab_a} but none in {lab_b} (closed/inactive?): " + ", ".join(z['nm'] for z in inactive[:8]) + ".")
    if new_stores:
        ins.append(f"{len(new_stores)} newly launched stores (no sales in {lab_a}) were excluded from the comparison.")
    import datetime as _dt
    if d_b_end > _dt.date.today().isoformat():
        ins.append(f"Note: {lab_b} is not complete yet, so comparison is partial.")

    # ---- Excel ----
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    hdr_fill = PatternFill('solid', fgColor='1F2A56')
    key_fill = PatternFill('solid', fgColor='FFF2CC')
    red, green = Font(color='C00000', bold=True), Font(color='2E7D32', bold=True)

    def sheet(ws, headers, data, num_cols=(), pct_cols=(), delta_cols=(), key_col=None):
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF'); c.fill = hdr_fill
            c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        for r in data:
            ws.append(r)
        for i in range(2, ws.max_row + 1):
            for ci in num_cols:
                ws.cell(i, ci).number_format = '#,##0'
            for ci in pct_cols:
                ws.cell(i, ci).number_format = '0.0%'
            for ci in delta_cols:
                v = ws.cell(i, ci).value
                if isinstance(v, (int, float)) and v != 0:
                    ws.cell(i, ci).font = red if v < 0 else green
            if key_col and ws.cell(i, key_col).value in KEY_CATS:
                for cc in range(1, len(headers) + 1):
                    ws.cell(i, cc).fill = key_fill
        for ci, h in enumerate(headers, 1):
            width = max([len(str(h))] + [len(str(ws.cell(i, ci).value or '')) for i in range(2, min(ws.max_row, 200) + 1)])
            ws.column_dimensions[get_column_letter(ci)].width = min(max(width + 2, 11), 48)
        ws.freeze_panes = 'A2'
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions

    ws0 = wb.active; ws0.title = 'Insights'
    ws0.append([f"Quarterly Insights: {lab_b} vs {lab_a}"]); ws0['A1'].font = Font(bold=True, size=14)
    ws0.append([f"Scope: {scope_txt}. Units are net of returns. Categories compared: {product if product else ', '.join(FOCUS_CATS)}."])
    ws0.append([f"Like-for-like rule: only stores that had sales in {lab_a} are compared." if lfl else "All stores included."])
    ws0.append([])
    for line in ins:
        ws0.append([line])
    ws0.column_dimensions['A'].width = 160
    for r in ws0.iter_rows(min_row=5):
        r[0].alignment = Alignment(wrap_text=True, vertical='top')

    ua_h, ub_h = f"Units {lab_a}", f"Units {lab_b}"
    ra_h, rb_h = f"Revenue {lab_a}", f"Revenue {lab_b}"
    ws1 = wb.create_sheet('Store Summary')
    sheet(ws1, ['Store Code', 'Store', ua_h, ub_h, 'Unit Change', 'Unit %', ra_h, rb_h, 'Revenue Change', 'Revenue %', 'Categories Declined', 'Categories Grown', 'Remark'],
          [[z['br'], z['nm'], z['ua'], z['ub'], z['ub'] - z['ua'], _pct(z['ub'], z['ua']), z['ra'], z['rb'], z['rb'] - z['ra'], _pct(z['rb'], z['ra']), z['dec'], z['inc'],
            ('No sales in ' + lab_b) if z['ub'] == 0 else ('Units down' if z['ub'] < z['ua'] else 'Units up')] for z in store_list],
          num_cols=(3, 4, 5, 7, 8, 9), pct_cols=(6, 10), delta_cols=(5, 9))

    ordered = sorted(pairs_dec, key=lambda x: (store_rank.get(x['br'], 0), x['ub'] - x['ua']))
    ordered_up = sorted(pairs_inc, key=lambda x: (store_rank_up.get(x['br'], 0), -(x['ub'] - x['ua'])))
    pair_hdr = ['Store Code', 'Store', 'Product Category', ua_h, ub_h, 'Unit Change', 'Unit %', ra_h, rb_h, 'Revenue Change']
    pair_row = lambda x: [x['br'], x['nm'], x['cat'], x['ua'], x['ub'], x['ub'] - x['ua'], _pct(x['ub'], x['ua']), x['ra'], x['rb'], x['rb'] - x['ra']]
    if show_more:
        ws2u = wb.create_sheet('Store x Product Growth')
        sheet(ws2u, pair_hdr, [pair_row(x) for x in ordered_up], num_cols=(4, 5, 6, 8, 9, 10), pct_cols=(7,), delta_cols=(6, 10), key_col=3)
    if show_less:
        ws2 = wb.create_sheet('Store x Product Decline')
        sheet(ws2, pair_hdr, [pair_row(x) for x in ordered], num_cols=(4, 5, 6, 8, 9, 10), pct_cols=(7,), delta_cols=(6, 10), key_col=3)

    ws3 = wb.create_sheet('Category Summary')
    sheet(ws3, ['Product Category', ua_h, ub_h, 'Unit Change', 'Unit %', ra_h, rb_h, 'Revenue Change', 'Stores Sold in Base', 'Stores Declined', 'Stores Grown'],
          [[c['cat'], c['ua'], c['ub'], c['ub'] - c['ua'], _pct(c['ub'], c['ua']), c['ra'], c['rb'], c['rb'] - c['ra'], c['sa'], c['sdec'], c['sinc']] for c in cat_list],
          num_cols=(2, 3, 4, 6, 7, 8), pct_cols=(5,), delta_cols=(4, 8), key_col=1)

    # Key products: category summary + store-level detail, placed right after the Insights sheet
    key_rows_cat = [c for k in KEY_CATS for c in [cats.get(k)] if c]
    if key_rows_cat and not product:
        wsk = wb.create_sheet('Key Products', 1)
        sheet(wsk, ['Key Product', ua_h, ub_h, 'Unit Change', 'Unit %', ra_h, rb_h, 'Revenue Change', 'Revenue %', 'Stores Grew', 'Stores Declined', 'Stores Sold (either period)'],
              [[c['cat'], c['ua'], c['ub'], c['ub'] - c['ua'], _pct(c['ub'], c['ua']), c['ra'], c['rb'], c['rb'] - c['ra'], _pct(c['rb'], c['ra']), c['sinc'], c['sdec'], c['sany']] for c in key_rows_cat],
              num_cols=(2, 3, 4, 6, 7, 8), pct_cols=(5, 9), delta_cols=(4, 8))
        wsks = wb.create_sheet('Key Products by Store', 2)
        key_pairs = sorted([x for x in rows if x['cat'] in KEY_CATS],
                           key=lambda x: (KEY_CATS.index(x['cat']), x['ub'] - x['ua']))
        sheet(wsks, ['Key Product', 'Store Code', 'Store', ua_h, ub_h, 'Unit Change', 'Unit %', ra_h, rb_h, 'Revenue Change'],
              [[x['cat'], x['br'], x['nm'], x['ua'], x['ub'], x['ub'] - x['ua'], _pct(x['ub'], x['ua']), x['ra'], x['rb'], x['rb'] - x['ra']] for x in key_pairs],
              num_cols=(4, 5, 6, 8, 9, 10), pct_cols=(7,), delta_cols=(6, 10))

    ws4 = wb.create_sheet('All Store x Product')
    full = sorted(rows, key=lambda x: (store_rank.get(x['br'], 0), x['ub'] - x['ua']))
    sheet(ws4, ['Store Code', 'Store', 'Product Category', ua_h, ub_h, 'Unit Change', 'Unit %', ra_h, rb_h, 'Revenue Change'],
          [[x['br'], x['nm'], x['cat'], x['ua'], x['ub'], x['ub'] - x['ua'], _pct(x['ub'], x['ua']), x['ra'], x['rb'], x['rb'] - x['ra']] for x in full],
          num_cols=(4, 5, 6, 8, 9, 10), pct_cols=(7,), delta_cols=(6, 10), key_col=3)

    if new_stores:
        ws5 = wb.create_sheet('Excluded New Stores')
        sheet(ws5, ['Store Code', 'Store', f'First Sale in {lab_b}', f'Revenue {lab_b}'],
              [[n['br'], n['nm'], str(n['first_sale']), float(n['rev'])] for n in new_stores], num_cols=(4,))

    os.makedirs(EXPORT_DIR, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    safe = re.sub(r'[^A-Za-z0-9]+', '_', f"{lab_b}_vs_{lab_a}_{branch_name or 'all_stores'}{'_' + product if product else ''}").strip('_')
    fname = f"insights_{safe}_{token}.xlsx"
    wb.save(os.path.join(EXPORT_DIR, fname))

    # ---- Chat response ----
    cats_txt = (f"Category compared: {product}" if product else "Categories compared: " + ", ".join(FOCUS_CATS))
    detail_txt = []
    if show_more: detail_txt.append(f"{len(pairs_inc):,} store-product gains")
    if show_less: detail_txt.append(f"{len(pairs_dec):,} store-product declines")
    answer = "**Quarterly insights**\n" + "\n".join(f"- {l}" for l in ins) + f"\n\n{cats_txt}.\n\nFull store x product detail is in the Excel file below ({' / '.join(detail_txt)})."
    if direction == 'more':
        top_rows = (ordered_up[:15])
    elif direction == 'both':
        top_rows = pairs_inc[:8] + pairs_dec[:8]
    else:
        top_rows = (ordered[:15] if branch_code else pairs_dec[:15])
    table = {"headers": ["Store", "Product", ua_h, ub_h, "Change"],
             "rows": [[x['nm'], x['cat'], f"{x['ua']:,}", f"{x['ub']:,}", f"{x['ub'] - x['ua']:+,} ({_fmt_pct(x['ub'], x['ua'])})"] for x in top_rows]}
    key_rows_tbl = [cats[k] for k in KEY_CATS if k in cats]
    if key_rows_tbl and not product:
        table = {"headers": ["\u2605 Key Product", ua_h, ub_h, "Unit Change", "Revenue Change", "Stores Grew / Fell"],
                 "rows": [[c['cat'], f"{c['ua']:,}", f"{c['ub']:,}", f"{c['ub'] - c['ua']:+,} ({_fmt_pct(c['ub'], c['ua'])})",
                           f"{_fmt_pct(c['rb'], c['ra'])}", f"{c['sinc']} / {c['sdec']}"] for c in key_rows_tbl]}
    cards = [
        {"label": f"Units {lab_a}", "value": f"{tot_ua:,}", "color": "#6b7280"},
        {"label": f"Units {lab_b}", "value": f"{tot_ub:,}", "color": "#2563eb"},
    ]
    if show_more:
        cards += [{"label": "Stores Grew", "value": f"{len(inc_stores)} / {len(store_list)}", "color": "#059669"},
                  {"label": "Store-Product Gains", "value": f"{len(pairs_inc):,}", "color": "#059669"}]
    if show_less:
        cards += [{"label": "Stores Declined", "value": f"{len(dec_stores)} / {len(store_list)}", "color": "#ef4444"},
                  {"label": "Store-Product Declines", "value": f"{len(pairs_dec):,}", "color": "#d97706"}]
    return {
        "answer": answer, "cards": cards, "table": table, "sql": sql.strip(),
        "download": {"url": f"/api/ai/download/{fname}", "filename": fname},
        "suggestions": [f"Insights {lab_b} vs {lab_a} for Balussery Future", f"Compare {lab_b} with {lab_a} excluding newly launched stores"]
    }

_BRANCH_MAP_CACHE = None

def get_branch_map():
    global _BRANCH_MAP_CACHE
    if _BRANCH_MAP_CACHE is not None:
        return _BRANCH_MAP_CACHE
    try:
        rows = run_sql("SELECT code, branch_name FROM branch_master") or []
        existing_codes = {str(r.get('code', '')).strip().upper() for r in rows}
        for sb_code, sb_name in [('GPF', 'GUNDLUPETE FUTURE'), ('MLF', 'MALAPPURAM FUTURE')]:
            if sb_code not in existing_codes:
                rows.append({'code': sb_code, 'branch_name': sb_name})
        b_map = {
            'GUNDLUPET FUTURE': ('GPF', 'GUNDLUPETE FUTURE'),
            'GUNDLUPET': ('GPF', 'GUNDLUPETE FUTURE'),
            'GUNDALPET': ('GPF', 'GUNDLUPETE FUTURE'),
        }
        for r in rows:
            code = r['code'].strip()
            name = r['branch_name'].strip()
            b_map[name.upper()] = (code, name)
            # Normalized without duplicate letters (e.g. mannarkkad -> mannarkad)
            norm_name = re.sub(r'([a-zA-Z])\1+', r'\1', name).upper()
            if norm_name != name.upper():
                b_map[norm_name] = (code, name)
            # Store code if 3+ chars
            if len(code) >= 3:
                b_map[code.upper()] = (code, name)
            # Town / first word if length >= 5
            town = name.split()[0].upper()
            if len(town) >= 5 and town not in b_map:
                b_map[town] = (code, name)
        _BRANCH_MAP_CACHE = b_map
        return _BRANCH_MAP_CACHE
    except Exception as e:
        print(f"[Branch Map Error] {e}")
        return {}

def extract_branch(text):
    b_map = get_branch_map()
    if not b_map:
        return None, None
    t_raw = text.upper()
    t_norm = re.sub(r'([A-Z])\1+', r'\1', t_raw)
    for k in sorted(b_map.keys(), key=len, reverse=True):
        if len(k) < 3:
            continue
        pattern = r'\b' + re.escape(k) + r'\b'
        if re.search(pattern, t_raw) or re.search(pattern, t_norm):
            return b_map[k]
    return None, None

_LATEST_DATE_CACHE = {'v': None, 't': 0}

def get_latest_sales_date():
    """Latest date present in azure_sales_report (cached 60s); falls back to today's date."""
    import time
    if _LATEST_DATE_CACHE['v'] and time.time() - _LATEST_DATE_CACHE['t'] < 60:
        return _LATEST_DATE_CACHE['v']
    try:
        rows = run_sql("SELECT toString(max(toDate(date))) AS d FROM azure_sales_report")
        v = rows[0]['d'] if rows and rows[0].get('d') else datetime.now().strftime('%Y-%m-%d')
    except Exception:
        v = datetime.now().strftime('%Y-%m-%d')
    _LATEST_DATE_CACHE['v'], _LATEST_DATE_CACHE['t'] = v, time.time()
    return v

def answer_with_nlp(question):
    """
    Deterministic semantic NLP engine that understands sales, products,
    brands, branches, and campaigns directly from ClickHouse.
    """
    q_low = question.lower().strip()
    
    start_date, end_date, date_label, is_month = extract_dates(question)
    if not start_date:
        # A single quarter / month span such as "JAS 2026" or "july august september 2026" -> that whole range
        _single = extract_periods(question)
        if len(_single) == 1:
            start_date, end_date, date_label, is_month = _single[0][0], _single[0][1], _single[0][2], False
    # Resolve the store first and remove its name from the text used for product/brand detection,
    # otherwise store names like "IRON BRIDGE FUTURE" are mistaken for products (iron).
    target_branch_code, target_branch_name = extract_branch(question)
    _q_prod = question
    if target_branch_name:
        _w = target_branch_name.split()
        for _n in range(len(_w), 0, -1):
            _pat = r'\b' + r'\s+'.join(re.escape(x) for x in _w[:_n]) + r'\b'
            if re.search(_pat, question, flags=re.I):
                _q_prod = re.sub(_pat, ' ', question, flags=re.I)
                break
    product, item_term, display_name = extract_product_and_item(_q_prod)
    brand = extract_brand(_q_prod)

    # Model-family names that customers use instead of product/brand (e.g. "iphone", "galaxy")
    if re.search(r'\b(iphones?|i\s+phones?)\b', question.lower()):
        product, item_term, display_name, brand = 'MOBILE', None, 'iPhone', 'APPLE'
    elif re.search(r'\bgalaxy\b', question.lower()):
        product, item_term, display_name, brand = 'MOBILE', None, 'Galaxy', 'SAMSUNG'
    target_branch_code, target_branch_name = extract_branch(question)

    is_qty_query = any(k in q_low for k in [
        'how many', 'quantity', 'units', 'volume', 'qty', 'count',
        'number of', 'how much unit', 'in terms of quantity', 'how much piece'
    ])

    is_compare = any(k in q_low for k in [
        'compare', 'comparison', 'previous year', 'last year', 'same date of previous year',
        'same date last year', 'yoy', 'year over year', 'vs last year', 'versus last year',
        'same day last year', 'same period last year', 'compared with', 'compared to'
    ])

    # Default date if not specified: latest date with sales in 2026
    # If question asks about "a specific date" without giving one, pick 2026-08-14 as the benchmark
    has_date = bool(start_date)
    if not start_date:
        latest = get_latest_sales_date()
        today_s = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime('%Y-%m-%d')
        if 'yesterday' in q_low:
            d = (datetime.utcnow() + timedelta(hours=5, minutes=30) - timedelta(days=1)).strftime('%Y-%m-%d')
            d = min(d, latest)
            date_label = datetime.strptime(d, '%Y-%m-%d').strftime('%d %b %Y')
        elif 'today' in q_low:
            d = min(today_s, latest)
            date_label = datetime.strptime(d, '%Y-%m-%d').strftime('%d %b %Y') + ('' if d == today_s else ' (latest available; no sales synced for today yet)')
        else:
            d = latest
            date_label = datetime.strptime(d, '%Y-%m-%d').strftime('%d %b %Y') + ' (latest available date - no date was specified)'
        start_date = end_date = d

    date_filter = f"toDate(s.date) = '{start_date}'" if start_date == end_date else f"toDate(s.date) >= '{start_date}' AND toDate(s.date) <= '{end_date}'"

    # Previous year date calculations for YoY comparison queries
    prev_start_date = None
    prev_end_date = None
    prev_date_label = None
    prev_date_filter = None
    if is_compare and start_date:
        try:
            s_dt = datetime.strptime(start_date, '%Y-%m-%d')
            prev_s_year = s_dt.year - 1
            day_s = min(s_dt.day, 28) if s_dt.month == 2 and s_dt.day == 29 else s_dt.day
            prev_s_dt = s_dt.replace(year=prev_s_year, day=day_s)
            prev_start_date = prev_s_dt.strftime('%Y-%m-%d')

            e_dt = datetime.strptime(end_date, '%Y-%m-%d')
            prev_e_year = e_dt.year - 1
            day_e = min(e_dt.day, 28) if e_dt.month == 2 and e_dt.day == 29 else e_dt.day
            prev_e_dt = e_dt.replace(year=prev_e_year, day=day_e)
            prev_end_date = prev_e_dt.strftime('%Y-%m-%d')

            prev_date_label = prev_s_dt.strftime('%d %b %Y') if start_date == end_date else f"{prev_s_dt.strftime('%d %b')} - {prev_e_dt.strftime('%d %b %Y')}"
            prev_date_filter = f"toDate(s.date) = '{prev_start_date}'" if prev_start_date == prev_end_date else f"toDate(s.date) >= '{prev_start_date}' AND toDate(s.date) <= '{prev_end_date}'"
        except Exception as e:
            print(f"[YoY Date Parse Error] {e}")
    # Direction: Least / Worst / Bottom vs Top / Best / Most
    is_least = any(k in q_low for k in [
        'least', 'lowest', 'worst', 'bottom', 'minimum', 'min', 'slowest',
        'underperformed', 'underperforming', 'poorest', 'poor'
    ])
    
    # Extract explicit limit if specified (e.g. "5 future stores", "top 3", "least 10")
    m_lim = re.search(r'\b(?:top|least|bottom|lowest|first)?\s*(\d{1,2})\s*(?:stores?|branches?|products?|items?|campaigns?|brands?)\b', q_low)
    if not m_lim:
        m_lim = re.search(r'\b(?:top|least|bottom|lowest)\s+(\d{1,2})\b', q_low)
    limit = int(m_lim.group(1)) if m_lim else 5
    if limit <= 0: limit = 5
    if limit > 50: limit = 50

    # 1. CAMPAIGN QUERIES
    if any(k in q_low for k in ['campaign', 'campaigns', 'group', 'roi', 'attribution', 'channel']):
        if any(k in q_low for k in ['top', 'best', 'highest', 'least', 'lowest', 'worst', 'bottom']) or is_least:
            order_clause = "ORDER BY purchase_value ASC" if is_least else "ORDER BY purchase_value DESC"
            rank_label = "lowest performing campaign" if is_least else "top performing campaign"
            card_color = "#ef4444" if is_least else "#4f46e5"
            sql = f"""
                SELECT campaign_name, type, start_date, target_size, purchase_count, 
                       purchase_value, roi, conversion_rate
                FROM campaign_dashboard_campaigns
                WHERE source_db = 'root' AND purchase_value > 0
                {order_clause}
                LIMIT {limit}
            """
            rows = run_sql(sql)
            if rows:
                top1 = rows[0]
                ans = f"The {rank_label} is **{top1['campaign_name']}** ({top1['type']}) with **{format_inr(top1['purchase_value'])}** in revenue, **{format_units(top1['purchase_count'])}** verified customer purchases, and an ROI of **{float(top1.get('roi') or 0):.0f}x**."
                cards = [
                    {"label": "Campaign", "value": top1['campaign_name'], "color": card_color},
                    {"label": "Revenue", "value": format_inr(top1['purchase_value']), "color": "#059669"},
                    {"label": "Purchases", "value": format_units(top1['purchase_count']), "color": "#2563eb"},
                    {"label": "ROI", "value": f"{float(top1.get('roi') or 0):.0f}x", "color": "#d97706"},
                ]
                table = {
                    "headers": ["Campaign Name", "Channel", "Start Date", "Revenue", "Purchases", "ROI"],
                    "rows": [[r['campaign_name'], r['type'], r['start_date'], format_inr_exact(r['purchase_value']), format_units(r['purchase_count']), f"{float(r.get('roi') or 0):.0f}x"] for r in rows]
                }
                return {
                    "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                    "suggestions": ["What was our overall campaign revenue?", "Show campaigns by channel", "Which product was most sold on 2026-08-14?"]
                }
        else:
            sql = """
                SELECT count() AS total_camps, 
                       sumIf(purchase_value, purchase_value > 0) AS total_rev,
                       sumIf(purchase_count, purchase_count > 0) AS total_purchases,
                       avgIf(roi, purchase_value > 0) AS avg_roi
                FROM campaign_dashboard_campaigns
                WHERE source_db = 'root'
            """
            rows = run_sql(sql)
            if rows:
                r = rows[0]
                ans = f"Across all campaigns in ClickHouse, **{format_units(r['total_camps'])} campaigns** have generated **{format_inr(r['total_rev'])}** in verified revenue across **{format_units(r['total_purchases'])} purchases**, achieving an average ROI of **{float(r.get('avg_roi') or 0):.0f}x**."
                cards = [
                    {"label": "Total Revenue", "value": format_inr(r['total_rev']), "color": "#059669"},
                    {"label": "Total Purchases", "value": format_units(r['total_purchases']), "color": "#2563eb"},
                    {"label": "Campaigns", "value": format_units(r['total_camps']), "color": "#4f46e5"},
                    {"label": "Avg ROI", "value": f"{float(r.get('avg_roi') or 0):.0f}x", "color": "#d97706"},
                ]
                return {
                    "answer": ans, "sql": sql.strip(), "cards": cards,
                    "suggestions": ["Top 5 campaigns by revenue", "What was the sale on 2026-08-14?", "Which product was most sold on 2026-08-14?"]
                }

    # 1a000. QUARTER-TO-QUARTER STORE ANALYSIS - "quarter to quarter analysis of <store>, product wise, declining products"
    if (target_branch_code and not item_term and not (product and not item_term)
            and re.search(r'quarter[\s-]*(to|on|over|vs\.?|by)[\s-]*quarter|\bqoq\b|quarter[\s-]*wise|quarterly\s+(analysis|trend|comparison|report|review|performance)|each\s+quarter|every\s+quarter|all\s+quarters', q_low)
            and not extract_periods(question)):
        try:
            import store_qoq
            return store_qoq.store_qoq(target_branch_code, target_branch_name, get_latest_sales_date())
        except Exception as _e:
            import traceback; traceback.print_exc()

    # 1a00. OVERALL STORE REVIEW - "overall report of <store> and give insights" (lifetime, internal + external)
    if (target_branch_code and not (product and not item_term) and not item_term
            and re.search(r'\b(overall|report|review|profile|scorecard|health|insights?|analy[sz]\w*|deep\s+dive)\b', q_low)
            and not re.search(r'\b(yesterday|today|last|this)\b', q_low)
            and not extract_dates(question)[0] and not extract_periods(question)):
        try:
            import store_review
            return store_review.store_review(target_branch_code, target_branch_name, get_latest_sales_date())
        except Exception as _e:
            import traceback; traceback.print_exc()

    # 1a0. QUARTERLY INSIGHTS + EXCEL - "insights JAS 2026 vs JAS 2025" (store x product declines, downloadable)
    if re.search(r'\b(insights?|deep\s+dive|analy[sz]e|analysis|excel|xlsx|spreadsheet|download|export)\b', q_low) and not extract_two_dates(question):
        ins_periods = extract_periods(question)
        if len(ins_periods) == 2:
            ins_periods.sort(key=lambda p: p[0])
            no_lfl = bool(re.search(r'\b(include|including|with)\s+(all|the)?\s*(new|newly)|all\s+stores\s+including', q_low))
            _less = bool(re.search(r'\b(less|least|lowest|bottom|slowest|low|decreas\w*|declin\w*|drop\w*|fell|fall\w*|lower|down|reduc\w*|dip\w*|lost|loss|worse|negative|under[\s-]?perform\w*|poor\w*|weak\w*|worst)\b', q_low))
            _more = bool(re.search(r'\b(more|increas\w*|grew|grow\w*|gain\w*|higher|rise|rose|improv\w*|better|positive)\b', q_low))
            direction = 'less' if (_less and not _more) else ('more' if (_more and not _less) else 'both')
            _qn = re.sub(r'(exclud\w*|without|including|include)?\s*(the\s+)?(new(ly)?\s+(launched\s+|opened\s+)?|like[\s-]*for[\s-]*like\s+|same\s+|existing\s+)stores?', ' ', q_low)
            _stype = None
            if not target_branch_code:
                if re.search(r'\bfuture\b', _qn): _stype = 'FUTURE'
                elif re.search(r'\bcare\s+stores?\b', _qn): _stype = 'CARE'
            return quarterly_insights(ins_periods[0], ins_periods[1], target_branch_code, target_branch_name,
                                      product if (product and not item_term) else None, lfl=not no_lfl, direction=direction, store_type=_stype)

    # 1a. TWO-DATE COMPARISON - "compare 04-09-2025 with 25-08-2026" -> which products sold more / less
    two_dates = extract_two_dates(question)
    cmp_periods = []
    if len(two_dates) == 2:
        cmp_periods = [(d, d, datetime.strptime(d, '%Y-%m-%d').strftime('%d-%m-%Y')) for d in two_dates]
    elif len(two_dates) == 0:
        cmp_periods = extract_periods(question)
        if len(cmp_periods) == 2:
            cmp_periods.sort(key=lambda p: p[0])  # base = earlier period, current = later
    if len(cmp_periods) == 2 and re.search(r'\b(compar\w*|vs\.?|versus|against|difference|differ\w*|previous year|last year|yoy)\b', q_low):
        (d_a, d_a_end, lab_a), (d_b, d_b_end, lab_b) = cmp_periods
        # Like-for-like is the DEFAULT for period (quarter / month-span) comparisons: stores with no sales in the base period are excluded.
        # Single-day comparisons keep all stores unless asked. Say "including new stores" to opt out.
        _is_period = (d_a != d_a_end) or (d_b != d_b_end)
        _optout = bool(re.search(r'\b(include|including|with)\s+(all\s+|the\s+)?(new|newly)|all\s+stores\s+including|without\s+(like[\s-]*for[\s-]*like|excluding)', q_low))
        lfl = (not _optout) and (_is_period or bool(re.search(r'like[\s-]*for[\s-]*like|\blfl\b|same[\s-]+stores?|existing\s+stores?|new(ly)?\s+(launched\s+|opened\s+)?stores?|exclud\w*\s+(the\s+)?(new|newly)', q_low)))
        in_a = f"toDate(s.date) BETWEEN '{d_a}' AND '{d_a_end}'"
        in_b = f"toDate(s.date) BETWEEN '{d_b}' AND '{d_b_end}'"
        lfl_filter, lfl_note = "", ""
        if lfl:
            lfl_filter = (f" AND s.branch IN (SELECT DISTINCT branch FROM azure_sales_report WHERE {in_a.replace('s.date','date')})")
            try:
                nrows = run_sql(f"""
                    SELECT s.branch AS br, coalesce(any(bm.branch_name), s.branch) AS nm,
                           sum(toFloat64(s.sold_price) * toInt64(s.qty)) AS rev
                    FROM azure_sales_report s LEFT JOIN branch_master bm ON bm.code = s.branch
                    WHERE {in_b} AND s.branch NOT IN ('SMC','3GH')
                      AND s.branch NOT IN (SELECT DISTINCT branch FROM azure_sales_report WHERE {in_a.replace('s.date','date')})
                    GROUP BY s.branch ORDER BY rev DESC
                """) or []
            except Exception:
                nrows = []
            names_x = ", ".join(str(r['nm']) for r in nrows[:10]) + (" ..." if len(nrows) > 10 else "")
            lfl_note = (f" Like-for-like: only stores that had sales in {lab_a} are compared; "
                        f"**{len(nrows)} newly launched store(s)** with no sales in {lab_a} were excluded"
                        f"{' (' + names_x + ')' if nrows else ''}.")
        excluded_c = ("'SCHEME','AC OUTDOOR','D SPARE','SPARE','GDP-SPARE','FIXED ASSETS','DEMO','DEMO ACCESSORIES',"
                      "'STATIONERY ITEMS','GIFT ITEMS','OFFER KIT','FOC','SERVICE','SERVICE CHARGES','OSG WARRANTY',"
                      "'CARE PLUS','LG AMC','GDOT CARE','TOTAL SECURITY','MOBILE ANTIVIRUS','CEGI','SMART CHOICE'")
        prod_expr_c = ("if(coalesce(im.product,'')='', multiIf(s.item_code LIKE 'MOB%','MOBILE', s.item_code LIKE 'TV%','TV', "
                       "s.item_code LIKE 'LAP%','LAPTOP', s.item_code LIKE 'AC%','AIR CONDITIONER', "
                       "s.item_code LIKE 'WM%','WASHING MACHINES', s.item_code LIKE 'REF%','REFRIGERATORS',''), im.product)")
        qty_c = "if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))"
        rev_c = "toFloat64(s.sold_price) * toInt64(s.qty)"
        extra = ""
        group_expr, group_title = prod_expr_c, "Product Category"
        scope_bits = []
        if target_branch_code:
            extra += f" AND s.branch = '{target_branch_code}'"
            scope_bits.append(target_branch_name)
        if item_term:
            extra += f" AND upper(im.item_name) LIKE '%{item_term}%'"
            group_expr, group_title = "coalesce(im.brand,'Other')", "Brand"
            scope_bits.append(display_name)
        elif product:
            extra += f" AND {prod_expr_c} = '{product}'"
            group_expr, group_title = "coalesce(im.brand,'Other')", "Brand"
            scope_bits.append(display_name)
        if brand and not (item_term or product):
            extra += f" AND upper(im.brand) = '{brand}'"
            scope_bits.append(brand)
        q_nostore = re.sub(r'(exclud\w*|without|including|include)?\s*(the\s+)?(new(ly)?\s+(launched\s+|opened\s+)?|like[\s-]*for[\s-]*like\s+|same\s+|existing\s+)stores?', ' ', q_low)
        store_mode = (not target_branch_code) and bool(re.search(
            r'\bwhich\b.*\b(stores?|branch(?:es)?|outlets?)\b|\b(store|branch)[\s-]*wise\b|\bby\s+(store|branch)|\b(each|every|per|list(?:\s+of)?)\s+(future\s+|care\s+)?(stores?|branch(?:es)?)\b|\b(future|care)\s+stores?\b',
            q_nostore))
        if store_mode:
            group_expr, group_title = "coalesce(bm.branch_name, s.branch)", "Store"
            if 'future' in q_nostore:
                extra += " AND upper(coalesce(bm.branch_name, s.branch)) LIKE '%FUTURE%'"
                scope_bits.append("Future stores")
            elif re.search(r'\bcare\b', q_nostore):
                extra += " AND upper(coalesce(bm.branch_name, s.branch)) LIKE '%CARE%'"
                scope_bits.append("Care stores")
        scope = " / ".join(scope_bits) if scope_bits else ("like-for-like stores" if lfl else "all stores")
        is_range_cmp = (d_a != d_a_end) or (d_b != d_b_end)
        use_focus = is_range_cmp and not (item_term or product)
        cat_filter = (f"{prod_expr_c} IN ({_FOCUS_SQL})" if use_focus else f"{prod_expr_c} != '' AND {prod_expr_c} NOT IN ({excluded_c})")
        cmp_sql = f"""
            SELECT {group_expr} AS grp,
                   sumIf({qty_c}, {in_a}) AS ua,
                   sumIf({qty_c}, {in_b}) AS ub,
                   sumIf({rev_c}, {in_a}) AS ra,
                   sumIf({rev_c}, {in_b}) AS rb
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            LEFT JOIN branch_master bm ON bm.code = s.branch
            WHERE (({in_a}) OR ({in_b})){lfl_filter}
              AND s.branch NOT IN ('SMC', '3GH')
              AND s.item_code NOT LIKE 'SRV%'
              AND {cat_filter}
              {extra}
            GROUP BY grp
        """
        c_rows = run_sql(cmp_sql)
        data = []
        for r in c_rows or []:
            ua, ub = int(float(r['ua'])), int(float(r['ub']))
            ra, rb = float(r['ra']), float(r['rb'])
            if ua == 0 and ub == 0 and ra == 0 and rb == 0:
                continue
            data.append({'name': r['grp'], 'ua': ua, 'ub': ub, 'ra': ra, 'rb': rb, 'du': ub - ua, 'dr': rb - ra})
        if data:
            tot_ua, tot_ub = sum(x['ua'] for x in data), sum(x['ub'] for x in data)
            tot_ra, tot_rb = sum(x['ra'] for x in data), sum(x['rb'] for x in data)
            pct = lambda new, old: (f"{(new - old) / old * 100:+.1f}%" if old else ("new" if new else "-"))
            want_less = bool(re.search(r'\b(less|least|lowest|bottom|slowest|low|decreas\w*|declin\w*|drop\w*|fell|fall\w*|lower|down|reduc\w*|dip\w*|lost|loss|worse|negative|under[\s-]?perform\w*|poor\w*|weak\w*|worst)\b', q_low))
            want_more = bool(re.search(r'\b(more|increas\w*|grew|grow\w*|gain\w*|higher|up|rise|rose|improv\w*|better|positive)\b', q_low))
            only_less = want_less and not want_more
            only_more = want_more and not want_less
            # For a single direction, list every product in that direction unless a top-N was asked for
            n_show = limit if (m_lim or not (only_less or only_more)) else (300 if store_mode else 50)
            gainers = sorted([x for x in data if x['du'] > 0], key=lambda x: (-x['du'], -x['dr']))
            losers = sorted([x for x in data if x['du'] < 0], key=lambda x: (x['du'], x['dr']))
            name_u = lambda x: f"**{x['name']}** ({x['ua']:,} \u2192 {x['ub']:,}, {x['du']:+,})"
            note = f"*(Change = {lab_b} minus {lab_a}; units net of returns; " + ("only the selected categories are compared.)*" if use_focus else "services, warranties, gifts, stationery, spares and demo items excluded.)*") + f"{lfl_note}"

            def row(x, mark):
                return [f"{mark} {x['name']}", f"{x['ua']:,}", f"{x['ub']:,}", f"{x['du']:+,} ({pct(x['ub'], x['ua'])})", f"{format_inr_exact(x['ra'])} \u2192 {format_inr_exact(x['rb'])}"]

            def subtotal(label, items):
                ua_, ub_ = sum(x['ua'] for x in items), sum(x['ub'] for x in items)
                ra_, rb_ = sum(x['ra'] for x in items), sum(x['rb'] for x in items)
                return [label, f"{ua_:,}", f"{ub_:,}", f"{ub_ - ua_:+,} ({pct(ub_, ua_)})", f"{format_inr_exact(ra_)} \u2192 {format_inr_exact(rb_)}"], ua_, ub_, ra_, rb_

            if only_less or only_more:
                items_all = losers if only_less else gainers
                items = items_all[:n_show]
                word = "less" if only_less else "more"
                plural = "product categories" if group_title == "Product Category" else ("stores" if group_title == "Store" else "brands")
                mark, color = ("\u25bc", "#ef4444") if only_less else ("\u25b2", "#059669")
                if not items_all:
                    return {"answer": f"Comparing **{lab_a}** with **{lab_b}** ({scope}): no {group_title.lower()} sold {word} on {lab_b} than on {lab_a}. {note}",
                            "sql": cmp_sql.strip(), "cards": [], "table": None, "suggestions": [f"Compare {lab_a} with {lab_b}"]}
                tot_row, ua_, ub_, ra_, rb_ = subtotal(f"TOTAL ({len(items_all)} sold {word})", items_all)
                shown_txt = "; ".join(name_u(x) for x in (items[:15] if store_mode else items))
                more_note = (f" Showing top {min(15, len(items))} here; all {len(items_all)} are in the table below." if (store_mode and len(items_all) > 15) else (f" Showing top {len(items)} of {len(items_all)}." if len(items_all) > len(items) else ""))
                ans = (f"**{len(items_all)} {plural} sold {word} on {lab_b} than on {lab_a}** ({scope}): "
                       f"{shown_txt}.{more_note} Together they went from **{ua_:,}** to **{ub_:,}** units "
                       f"(**{ub_ - ua_:+,}**) and revenue moved from **{format_inr(ra_)}** to **{format_inr(rb_)}**. {note}")
                cards = [
                    {"label": f"{plural.title()} Sold {word.title()}", "value": f"{len(items_all)}", "color": color},
                    {"label": f"Units {lab_a}", "value": f"{ua_:,}", "color": "#6b7280"},
                    {"label": f"Units {lab_b}", "value": f"{ub_:,}", "color": "#2563eb"},
                    {"label": "Unit Change", "value": f"{ub_ - ua_:+,} ({pct(ub_, ua_)})", "color": color},
                ]
                rows_t = [row(x, mark) for x in items] + [tot_row]
            else:
                items = gainers[:n_show] + losers[:n_show]
                more_txt = "; ".join(name_u(x) for x in gainers[:n_show]) or "none"
                less_txt = "; ".join(name_u(x) for x in losers[:n_show]) or "none"
                ans = (f"Comparing **{lab_a}** with **{lab_b}** ({scope}): total units went from **{tot_ua:,}** to **{tot_ub:,}** "
                       f"(**{tot_ub - tot_ua:+,}**, {pct(tot_ub, tot_ua)}) and revenue from **{format_inr(tot_ra)}** to **{format_inr(tot_rb)}** "
                       f"(**{format_inr(tot_rb - tot_ra)}**, {pct(tot_rb, tot_ra)}). "
                       f"**Sold more on {lab_b}:** {more_txt}. **Sold less on {lab_b}:** {less_txt}. {note}")
                rows_t = [row(x, '\u25b2') for x in gainers[:n_show]] + [row(x, '\u25bc') for x in losers[:n_show]]
                rows_t.append(["TOTAL", f"{tot_ua:,}", f"{tot_ub:,}", f"{tot_ub - tot_ua:+,} ({pct(tot_ub, tot_ua)})", f"{format_inr_exact(tot_ra)} \u2192 {format_inr_exact(tot_rb)}"])
                cards = [
                    {"label": f"Units {lab_a}", "value": f"{tot_ua:,}", "color": "#6b7280"},
                    {"label": f"Units {lab_b}", "value": f"{tot_ub:,}", "color": "#2563eb"},
                    {"label": "Unit Change", "value": f"{tot_ub - tot_ua:+,} ({pct(tot_ub, tot_ua)})", "color": "#059669" if tot_ub >= tot_ua else "#ef4444"},
                    {"label": "Revenue Change", "value": f"{format_inr(tot_rb - tot_ra)} ({pct(tot_rb, tot_ra)})", "color": "#059669" if tot_rb >= tot_ra else "#ef4444"}
                ]
            if use_focus:
                key_d = [x for k in KEY_CATS for x in data if x['name'] == k and not (only_less and x['du'] >= 0) and not (only_more and x['du'] <= 0)]
                if key_d:
                    ans = ("**\u2605 Key products:** " + "; ".join(f"**{x['name']}** {x['ua']:,} \u2192 {x['ub']:,} ({x['du']:+,}, {pct(x['ub'], x['ua'])})" for x in key_d) + "\n\n") + ans
                    _nm = lambda r: r[0].split(' ', 1)[1] if r[0][:1] in ('\u25b2', '\u25bc') and ' ' in r[0] else r[0]
                    tot_rows = [r for r in rows_t if r[0].startswith('TOTAL')]
                    body = [r for r in rows_t if not r[0].startswith('TOTAL')]
                    body.sort(key=lambda r: 0 if _nm(r) in KEY_CATS else 1)
                    rows_t = [(['\u2605 ' + r[0]] + r[1:]) if _nm(r) in KEY_CATS else r for r in body] + tot_rows
            table = {"headers": [group_title, f"Units {lab_a}", f"Units {lab_b}", "Change", "Revenue"], "rows": rows_t}
            return {
                "answer": ans, "sql": cmp_sql.strip(), "cards": cards, "table": table,
                "suggestions": [f"Which product sold the most on {lab_b}?", f"Compare {lab_a} with {lab_b} for Balussery Future", f"What was the total sale on {d_b}?"]
            }

    # 1b. PRODUCT RANKING - "which product sold the most/least on <date>" (all stores or one store)
    rank_intent = bool(re.search(r'\b(most|least|highest|lowest|top|best|worst|bottom|selling|slowest|fastest)\b', q_low)) \
        and bool(re.search(r'\b(products?|items?|categor(?:y|ies)|models?)\b', q_low))
    # "which product sold more / less (in terms of units)" on a date / period / store
    _which_more = bool(re.search(r'\bwhich\b.*\b(products?|items?|categor(?:y|ies)|models?)\b.*\b(sold|sell|sells|selling)\s+(the\s+)?(more|less|lesser|fewer)\b', q_low)) \
        or bool(re.search(r'\bwhich\b.*\b(products?|items?|categor(?:y|ies)|models?)\b.*\b(more|less)\s+(in\s+terms\s+of|by)\b', q_low))
    if _which_more:
        rank_intent = True
        if re.search(r'\b(less|lesser|fewer)\b', q_low):
            is_least = True
    if (rank_intent or any(k in q_low for k in ['product breakdown', 'sold the most', 'sold most', 'most sold', 'best selling', 'top selling'])) \
            and not (product or item_term) \
            and (bool(target_branch_code) or not any(k in q_low for k in ['store', 'stores', 'branches', 'branch'])):
        by_revenue = any(k in q_low for k in ['revenue', 'sales value', 'amount', 'value', 'turnover', 'worth'])
        excluded = ("'SCHEME','AC OUTDOOR','D SPARE','SPARE','GDP-SPARE','FIXED ASSETS','DEMO','DEMO ACCESSORIES',"
                    "'STATIONERY ITEMS','GIFT ITEMS','OFFER KIT','FOC','SERVICE','SERVICE CHARGES','OSG WARRANTY',"
                    "'CARE PLUS','LG AMC','GDOT CARE','TOTAL SECURITY','MOBILE ANTIVIRUS','CEGI','SMART CHOICE'")
        prod_expr = ("if(coalesce(im.product,'')='', multiIf(s.item_code LIKE 'MOB%','MOBILE', s.item_code LIKE 'TV%','TV', "
                     "s.item_code LIKE 'LAP%','LAPTOP', s.item_code LIKE 'AC%','AIR CONDITIONER', "
                     "s.item_code LIKE 'WM%','WASHING MACHINES', s.item_code LIKE 'REF%','REFRIGERATORS',''), im.product)")
        net_units = "sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty)))"
        branch_cond = f"AND s.branch = '{target_branch_code}'" if target_branch_code else ""
        scope = target_branch_name if target_branch_code else "all stores"
        base_where = (f"WHERE {date_filter} AND s.branch NOT IN ('SMC', '3GH') {branch_cond} "
                      f"AND s.item_code NOT LIKE 'SRV%' AND {prod_expr} != '' AND {prod_expr} NOT IN ({excluded})")
        if by_revenue:
            order = "revenue ASC, units ASC" if is_least else "revenue DESC, units DESC"
        else:
            order = "units ASC, revenue ASC" if is_least else "units DESC, revenue DESC"
        having = "HAVING units > 0" if is_least else ""
        sql = f"""
            SELECT {prod_expr} AS product,
                   {net_units} AS units,
                   round(sum(toFloat64(s.sold_price) * toInt64(s.qty)), 2) AS revenue
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            {base_where}
            GROUP BY product
            {having}
            ORDER BY {order}
            LIMIT {limit}
        """
        rows = run_sql(sql)
        if rows:
            for r in rows:
                r['units'] = int(float(r['units'])); r['revenue'] = float(r['revenue'])
            top = rows[0]
            # Leader by the *other* metric, so both "sold most" and "earned most" are answered exactly
            alt_sql = f"""
                SELECT {prod_expr} AS product, {net_units} AS units,
                       round(sum(toFloat64(s.sold_price) * toInt64(s.qty)), 2) AS revenue
                FROM azure_sales_report s LEFT JOIN item_master im ON im.item_code = s.item_code
                {base_where}
                GROUP BY product {having}
                ORDER BY {'units' if by_revenue else 'revenue'} {'ASC' if is_least else 'DESC'} LIMIT 1
            """
            alt = run_sql(alt_sql)
            alt_txt = ""
            alt_row = alt[0] if alt else None
            if alt_row and alt_row['product'] != top['product']:
                if by_revenue:
                    alt_txt = f" By units, **{alt_row['product']}** was {'lowest' if is_least else 'highest'} with **{format_units(int(float(alt_row['units'])))} units**."
                else:
                    alt_txt = f" By revenue, **{alt_row['product']}** was {'lowest' if is_least else 'highest'} with **{format_inr(alt_row['revenue'])}** ({format_inr_exact(alt_row['revenue'])})."

            # Top models (individual items) for the same scope
            top_prod_sql = str(top['product']).replace("'", "''")
            m_sql = f"""
                SELECT coalesce(im.item_name, s.item_code) AS model, {net_units} AS units,
                       round(sum(toFloat64(s.sold_price) * toInt64(s.qty)), 2) AS revenue
                FROM azure_sales_report s LEFT JOIN item_master im ON im.item_code = s.item_code
                {base_where} AND {prod_expr} = '{top_prod_sql}'
                GROUP BY model HAVING units > 0
                ORDER BY {'revenue' if by_revenue else 'units'} {'ASC' if is_least else 'DESC'} LIMIT 3
            """
            m_rows = run_sql(m_sql)
            model_txt = ""
            if m_rows:
                model_txt = f" Top {top['product']} models: " + "; ".join(f"**{m['model']}** ({int(float(m['units']))} unit{'s' if int(float(m['units'])) != 1 else ''})" for m in m_rows) + "."

            metric_word = "revenue" if by_revenue else "units sold"
            direction = "least" if is_least else "most"
            ans = (f"On **{date_label}** at **{scope}**, the product category that sold the {direction} by {metric_word} was "
                   f"**{top['product']}** with **{format_units(top['units'])} units** and **{format_inr(top['revenue'])}** "
                   f"({format_inr_exact(top['revenue'])}).{alt_txt}{model_txt} "
                   f"*(Units are net of returns; services, warranties, gifts, stationery, spares and demo items are excluded.)*")
            cards = [
                {"label": f"{'Lowest' if is_least else 'Top'} Category", "value": top['product'], "color": "#ef4444" if is_least else "#4f46e5"},
                {"label": "Units Sold", "value": format_units(top['units']), "color": "#2563eb"},
                {"label": "Revenue", "value": format_inr(top['revenue']), "color": "#059669"},
                {"label": "Scope", "value": scope, "color": "#7c3aed"}
            ]
            table = {
                "headers": ["Product Category", "Units Sold", "Revenue"],
                "rows": [[r['product'], format_units(r['units']), format_inr_exact(r['revenue'])] for r in rows]
            }
            return {
                "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                "suggestions": [f"How much {top['product'].title()} was sold on {start_date}?",
                                f"Which product sold the most by revenue on {start_date}?",
                                f"What was the total sale on {start_date}?"]
            }

    # 2. SPECIFIC PRODUCT / ITEM SALES (e.g. "how many ceiling fan sold", "tv sales", "samsung mobile sold", etc.)
    if product or item_term:
        if item_term == 'PEDESTAL FAN':
            item_cond = "(upper(im.item_name) LIKE '%PEDESTAL FAN%' OR upper(im.item_name) LIKE '%PEDESTAL%') AND coalesce(im.product, '') NOT IN ('OSG WARRANTY', 'FIXED ASSETS', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
        elif item_term == 'WALL FAN':
            item_cond = "(upper(im.item_name) LIKE '%WALL FAN%' OR upper(im.item_name) LIKE '%WALL MOUNT%') AND coalesce(im.product, '') NOT IN ('OSG WARRANTY', 'FIXED ASSETS', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
        elif item_term == 'TABLE FAN':
            item_cond = "(upper(im.item_name) LIKE '%TABLE FAN%' OR upper(im.item_name) LIKE '%DESK FAN%') AND coalesce(im.product, '') NOT IN ('OSG WARRANTY', 'FIXED ASSETS', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
        elif item_term == 'CEILING FAN':
            item_cond = "(upper(im.item_name) LIKE '%CEILING FAN%' OR upper(im.item_name) LIKE '%CEILING%') AND coalesce(im.product, '') NOT IN ('OSG WARRANTY', 'FIXED ASSETS', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
        elif item_term == 'EXHAUST FAN':
            item_cond = "upper(im.item_name) LIKE '%EXHAUST%' AND coalesce(im.product, '') NOT IN ('OSG WARRANTY', 'FIXED ASSETS', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
        elif item_term == 'MICROWAVE':
            item_cond = "(im.product = 'MICROWAVE OVEN' OR upper(im.item_name) LIKE '%MICROWAVE%' OR upper(im.item_name) LIKE '%CONVECTION%') AND coalesce(im.product, '') NOT IN ('OSG WARRANTY', 'FIXED ASSETS', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
        elif item_term:
            item_cond = f"upper(im.item_name) LIKE '%{item_term}%' AND coalesce(im.product, '') NOT IN ('OSG WARRANTY', 'FIXED ASSETS', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
        else:
            if product == 'TV':
                item_cond = "(upper(im.product) = 'TV' OR im.item_category = 'Tv 18 %' OR s.item_code LIKE 'TV%') AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'MOBILE':
                item_cond = "(upper(im.product) = 'MOBILE' OR (s.item_code LIKE 'MOB%' AND coalesce(im.product, '') != 'MOBILE ANTIVIRUS')) AND coalesce(im.product, '') NOT IN ('SCHEME', 'MOBILE ANTIVIRUS', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'LAPTOP':
                item_cond = "(upper(im.product) = 'LAPTOP' OR s.item_code LIKE 'LAP%') AND coalesce(im.product, '') NOT IN ('SCHEME', 'LAPTOP BAG', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'AIR CONDITIONER':
                item_cond = "(upper(im.product) = 'AIR CONDITIONER' OR (s.item_code LIKE 'AC%' AND coalesce(im.product, '') = '')) AND coalesce(im.product, '') NOT IN ('AC OUTDOOR', 'SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'REFRIGERATORS':
                item_cond = "(upper(im.product) IN ('REFRIGERATORS', 'FREEZER') OR s.item_code LIKE 'REF%') AND coalesce(im.product, '') NOT IN ('SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'WASHING MACHINES':
                item_cond = "(upper(im.product) = 'WASHING MACHINES' OR s.item_code LIKE 'WSM%' OR s.item_code LIKE 'WM%') AND coalesce(im.product, '') NOT IN ('SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'TABLET':
                item_cond = "(upper(im.product) = 'TABLET' OR s.item_code LIKE 'TAB%') AND coalesce(im.product, '') NOT IN ('SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'SMART WATCH':
                item_cond = "upper(im.product) = 'SMART WATCH' AND coalesce(im.product, '') NOT IN ('SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
            elif product == 'EAR WEARABLES':
                item_cond = "upper(im.product) = 'EAR WEARABLES' AND coalesce(im.product, '') NOT IN ('SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
            else:
                item_cond = f"upper(im.product) = '{product}' AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'DEMO', 'DEMO ACCESSORIES')"

        if brand:
            item_cond += f" AND upper(im.brand) = '{brand}'"
            display_title = f"{brand} {display_name}"
        else:
            display_title = display_name

        if target_branch_code:
            item_cond += f" AND s.branch = '{target_branch_code}'"
            display_title = f"{display_title} at {target_branch_name}"

        sql = f"""
            SELECT sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units,
                   count(DISTINCT if(s.sold_price > 0 AND s.invoice_no NOT LIKE '%-SR-%', s.invoice_no, null)) as invoices,
                   count(DISTINCT s.branch) as branches
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND s.branch NOT IN ('SMC', '3GH')
              AND {item_cond}
        """
        rows = run_sql(sql)
        rev = float(rows[0]['revenue']) if rows and rows[0].get('revenue') is not None else 0
        units = int(float(rows[0]['units'])) if rows and rows[0].get('units') is not None else 0
        invoices = int(float(rows[0]['invoices'])) if rows and rows[0].get('invoices') is not None else 0
        branches = int(float(rows[0]['branches'])) if rows and rows[0].get('branches') is not None else 0

        # Check if user requested a comparison with previous year
        if is_compare and prev_date_filter:
            prev_sql = f"""
                SELECT sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                       sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units,
                       count(DISTINCT if(s.sold_price > 0 AND s.invoice_no NOT LIKE '%-SR-%', s.invoice_no, null)) as invoices,
                       count(DISTINCT s.branch) as branches
                FROM azure_sales_report s
                LEFT JOIN item_master im ON im.item_code = s.item_code
                WHERE {prev_date_filter}
                  AND s.branch NOT IN ('SMC', '3GH')
                  AND {item_cond}
            """
            prev_rows = run_sql(prev_sql)
            rev_prev = float(prev_rows[0]['revenue']) if prev_rows and prev_rows[0].get('revenue') is not None else 0
            units_prev = int(float(prev_rows[0]['units'])) if prev_rows and prev_rows[0].get('units') is not None else 0
            inv_prev = int(float(prev_rows[0]['invoices'])) if prev_rows and prev_rows[0].get('invoices') is not None else 0

            diff_units = units - units_prev
            pct_units = (diff_units / units_prev * 100) if units_prev > 0 else 0
            diff_rev = rev - rev_prev
            pct_rev = (diff_rev / rev_prev * 100) if rev_prev > 0 else 0

            trend_u = f"{diff_units:+d} ({pct_units:+.1f}%)"
            trend_r = f"{format_inr(diff_rev)} ({pct_rev:+.1f}%)"
            growth_word = "growth" if diff_units >= 0 else "decline"
            u_color = "#059669" if diff_units >= 0 else "#ef4444"
            r_color = "#059669" if diff_rev >= 0 else "#ef4444"

            ans = (
                f"On **{date_label}**, a total of **{format_units(units)} units** of **{display_title}** were sold "
                f"generating **{format_inr(rev)}** ({format_inr_exact(rev)} across {format_units(invoices)} customer invoices), "
                f"compared to **{format_units(units_prev)} units** ({format_inr(rev_prev)} across {format_units(inv_prev)} invoices) "
                f"on **{prev_date_label}** of previous year (**{trend_u} units**, **{pct_rev:+.1f}% revenue {growth_word}**)."
            )

            cards = [
                {"label": f"{date_label} Units", "value": f"{format_units(units)} units", "color": "#2563eb"},
                {"label": f"{prev_date_label} Units", "value": f"{format_units(units_prev)} units", "color": "#6b7280"},
                {"label": "Unit Growth (YoY)", "value": trend_u, "color": u_color},
                {"label": "Revenue Growth (YoY)", "value": trend_r, "color": r_color}
            ]

            table = {
                "headers": ["Metric", date_label, prev_date_label, "YoY Variance"],
                "rows": [
                    ["Units Sold", f"{units:,} units", f"{units_prev:,} units", trend_u],
                    ["Total Revenue", format_inr_exact(rev), format_inr_exact(rev_prev), trend_r],
                    ["Customer Invoices", f"{invoices:,}", f"{inv_prev:,}", f"{invoices - inv_prev:+d}"],
                    ["Avg Selling Price (ASP)", format_inr(rev / max(units, 1)), format_inr(rev_prev / max(units_prev, 1)), f"{format_inr((rev / max(units, 1)) - (rev_prev / max(units_prev, 1)))}"]
                ]
            }

            return {
                "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                "suggestions": [
                    f"Top brands for {display_title} on {start_date}",
                    f"What was total company revenue on {start_date}?",
                    f"Compare total sales on {start_date} with previous year"
                ]
            }

        # Query top brands if no specific brand was requested
        b_rows = []
        top_brand_txt = ""
        if not brand:
            b_sql = f"""
                SELECT coalesce(nullIf(trim(im.brand), ''), 'Unmapped POS SKU') as brand,
                       sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units,
                       sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue
                FROM azure_sales_report s
                LEFT JOIN item_master im ON im.item_code = s.item_code
                WHERE {date_filter}
                  AND s.branch NOT IN ('SMC', '3GH')
                  AND {item_cond}
                GROUP BY brand
                ORDER BY {'units' if is_qty_query else 'revenue'} DESC
                LIMIT 5
            """
            b_rows = run_sql(b_sql)
            if b_rows:
                if is_qty_query:
                    top_brand_txt = f" Top brand was **{b_rows[0]['brand']}** with **{format_units(b_rows[0]['units'])} units**."
                else:
                    top_brand_txt = f" Top brand was **{b_rows[0]['brand']}** with **{format_inr(b_rows[0]['revenue'])}** ({format_units(b_rows[0]['units'])} units)."

        if is_qty_query:
            ans = f"On **{date_label}**, a total of **{format_units(units)} units** of **{display_title}** were sold across **{branches} branches** (generating **{format_inr(rev)}** in revenue across {format_units(invoices)} customer invoices).{top_brand_txt}"
            cards = [
                {"label": f"{display_title} Units Sold", "value": format_units(units), "color": "#059669"},
                {"label": "Total Revenue", "value": format_inr(rev), "color": "#2563eb"},
                {"label": "Invoices", "value": format_units(invoices), "color": "#7c3aed"},
                {"label": "Active Stores", "value": format_units(branches), "color": "#d97706"}
            ]
            table = None
            if b_rows:
                table = {
                    "headers": ["Brand", "Units Sold", "Revenue"],
                    "rows": [[r['brand'], format_units(r['units']), format_inr_exact(r['revenue'])] for r in b_rows]
                }
        else:
            ans = f"On **{date_label}**, total **{display_title}** sales were **{format_inr(rev)}** ({format_inr_exact(rev)}) with **{format_units(units)} units** sold across **{branches} branches**.{top_brand_txt}"
            cards = [
                {"label": f"Total {display_title} Revenue", "value": format_inr(rev), "color": "#059669"},
                {"label": "Units Sold", "value": format_units(units), "color": "#2563eb"},
                {"label": "Invoices", "value": format_units(invoices), "color": "#7c3aed"},
                {"label": "Date", "value": date_label, "color": "#d97706"}
            ]
            table = None
            if b_rows:
                table = {
                    "headers": ["Brand", "Revenue", "Units Sold"],
                    "rows": [[r['brand'], format_inr_exact(r['revenue']), format_units(r['units'])] for r in b_rows]
                }

        return {
            "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
            "suggestions": [f"Top brands for {display_title} on {start_date}", f"What was the total sale on {start_date}?", f"Top branches for {display_title} on {start_date}"]
        }

    # 3. SINGLE BRANCH / STORE SALES (e.g. "what is total revenue on 01-06-2026 by balussery future")
    if target_branch_code:
        sql = f"""
            SELECT sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units,
                   count(DISTINCT if(s.sold_price > 0 AND s.invoice_no NOT LIKE '%-SR-%', s.invoice_no, null)) as invoices
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND s.branch = '{target_branch_code}'
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'DEMO', 'DEMO ACCESSORIES')
        """
        rows = run_sql(sql)
        rev = float(rows[0]['revenue']) if rows and rows[0].get('revenue') is not None else 0
        units = int(float(rows[0]['units'])) if rows and rows[0].get('units') is not None else 0
        invoices = int(float(rows[0]['invoices'])) if rows and rows[0].get('invoices') is not None else 0

        # Check if user requested a comparison with previous year
        if is_compare and prev_date_filter:
            prev_sql = f"""
                SELECT sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                       sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units,
                       count(DISTINCT if(s.sold_price > 0 AND s.invoice_no NOT LIKE '%-SR-%', s.invoice_no, null)) as invoices
                FROM azure_sales_report s
                LEFT JOIN item_master im ON im.item_code = s.item_code
                WHERE {prev_date_filter}
                  AND s.branch = '{target_branch_code}'
                  AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'DEMO', 'DEMO ACCESSORIES')
            """
            prev_rows = run_sql(prev_sql)
            rev_prev = float(prev_rows[0]['revenue']) if prev_rows and prev_rows[0].get('revenue') is not None else 0
            units_prev = int(float(prev_rows[0]['units'])) if prev_rows and prev_rows[0].get('units') is not None else 0
            inv_prev = int(float(prev_rows[0]['invoices'])) if prev_rows and prev_rows[0].get('invoices') is not None else 0

            diff_units = units - units_prev
            pct_units = (diff_units / units_prev * 100) if units_prev > 0 else 0
            diff_rev = rev - rev_prev
            pct_rev = (diff_rev / rev_prev * 100) if rev_prev > 0 else 0
            trend_u = f"{diff_units:+d} ({pct_units:+.1f}%)"
            trend_r = f"{format_inr(diff_rev)} ({pct_rev:+.1f}%)"
            growth_word = "growth" if diff_rev >= 0 else "decline"
            u_color = "#059669" if diff_units >= 0 else "#ef4444"
            r_color = "#059669" if diff_rev >= 0 else "#ef4444"

            ans = (
                f"On **{date_label}**, **{target_branch_name}** generated **{format_inr(rev)}** ({format_inr_exact(rev)}) "
                f"with **{format_units(units)} units** sold across {format_units(invoices)} invoices, compared to "
                f"**{format_inr(rev_prev)}** ({format_units(units_prev)} units across {format_units(inv_prev)} invoices) "
                f"on **{prev_date_label}** of previous year (**{trend_r} revenue {growth_word}**, {trend_u} units)."
            )
            cards = [
                {"label": f"{date_label} Sales", "value": format_inr(rev), "color": "#2563eb"},
                {"label": f"{prev_date_label} Sales", "value": format_inr(rev_prev), "color": "#6b7280"},
                {"label": "Revenue Growth (YoY)", "value": trend_r, "color": r_color},
                {"label": "Unit Growth (YoY)", "value": trend_u, "color": u_color}
            ]
            table = {
                "headers": ["Metric", date_label, prev_date_label, "YoY Variance"],
                "rows": [
                    ["Net Sales Revenue", format_inr_exact(rev), format_inr_exact(rev_prev), trend_r],
                    ["Units Sold", f"{units:,} units", f"{units_prev:,} units", trend_u],
                    ["Customer Invoices", f"{invoices:,}", f"{inv_prev:,}", f"{invoices - inv_prev:+d}"],
                    ["Avg Order Value (AOV)", format_inr_exact(rev / max(invoices, 1)), format_inr_exact(rev_prev / max(inv_prev, 1)), f"{format_inr_exact((rev / max(invoices, 1)) - (rev_prev / max(inv_prev, 1)))}"]
                ]
            }
            return {
                "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                "suggestions": [
                    f"Top products at {target_branch_name} on {start_date}",
                    f"How much Mobile was sold in {target_branch_name} on {start_date}?",
                    f"What was total company revenue on {start_date}?"
                ]
            }

        # Query top product categories for this store on this date
        p_sql = f"""
            SELECT if({PROD_EXPR} = '', 'Other', {PROD_EXPR}) as product,
                   sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units,
                   round(sum(toFloat64(s.sold_price) * toInt64(s.qty)), 2) as revenue
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND s.branch = '{target_branch_code}'
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'DEMO', 'DEMO ACCESSORIES')
            GROUP BY product
            ORDER BY revenue DESC
            LIMIT 5
        """
        p_rows = run_sql(p_sql)
        top_prod_txt = ""
        if p_rows:
            top_prod_txt = f" Leading category was **{p_rows[0]['product']}** with **{format_inr(p_rows[0]['revenue'])}** ({format_units(p_rows[0]['units'])} units)."

        ans = f"On **{date_label}**, **{target_branch_name}** generated **{format_inr(rev)}** ({format_inr_exact(rev)}) in net sales with **{format_units(units)} units** sold across **{format_units(invoices)} customer invoices**.{top_prod_txt}"
        cards = [
            {"label": "Store Net Sales", "value": format_inr(rev), "color": "#059669"},
            {"label": "Units Sold", "value": format_units(units), "color": "#2563eb"},
            {"label": "Customer Invoices", "value": format_units(invoices), "color": "#7c3aed"},
            {"label": "Store Branch", "value": target_branch_name, "color": "#d97706"}
        ]
        table = None
        if p_rows:
            table = {
                "headers": ["Product Category", "Revenue", "Units Sold"],
                "rows": [[r['product'], format_inr_exact(r['revenue']), format_units(r['units'])] for r in p_rows]
            }

        return {
            "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
            "suggestions": [
                f"How much Mobile was sold in {target_branch_name} on {start_date}?",
                f"How much TV was sold in {target_branch_name} on {start_date}?",
                f"What was the total company sales on {start_date}?"
            ]
        }

    # 4. MOST / LEAST SOLD PRODUCT (e.g. "which product was most sold on this date" or "least sold product")
    if any(k in q_low for k in ['most sold', 'top product', 'top selling product', 'highest sold product', 'product breakdown', 'least sold', 'lowest sold', 'worst sold', 'least product', 'lowest product']):
        order_clause = "ORDER BY revenue ASC" if is_least else "ORDER BY revenue DESC"
        having_clause = "HAVING revenue > 0" if is_least else ""
        rank_word = "least sold product" if is_least else "most sold product"
        card_label = "Lowest Product" if is_least else "Top Product"
        card_color = "#ef4444" if is_least else "#4f46e5"

        sql = f"""
            SELECT if({PROD_EXPR} = '', 'Other', {PROD_EXPR}) as product,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND s.branch NOT IN ('SMC', '3GH')
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'D SPARE', 'SPARE', 'FIXED ASSETS', 'DEMO', 'DEMO ACCESSORIES')
            GROUP BY product
            {having_clause}
            {order_clause}
            LIMIT {limit}
        """
        rows = run_sql(sql)
        if rows:
            top1 = rows[0]
            ans = f"On **{date_label}**, the {rank_word} by revenue was **{top1['product']}**, generating **{format_inr(top1['revenue'])}** ({format_inr_exact(top1['revenue'])}) with **{format_units(top1['units'])} units** sold."
            cards = [
                {"label": card_label, "value": top1['product'], "color": card_color},
                {"label": "Product Revenue", "value": format_inr(top1['revenue']), "color": "#059669"},
                {"label": "Product Units", "value": format_units(top1['units']), "color": "#2563eb"},
                {"label": "Date", "value": date_label, "color": "#7c3aed"}
            ]
            table = {
                "headers": ["Product Category", "Revenue", "Units Sold"],
                "rows": [[r['product'], format_inr_exact(r['revenue']), format_units(r['units'])] for r in rows]
            }
            return {
                "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                "suggestions": [f"How much {top1['product']} was sold on {start_date}?", f"What was the total sale on {start_date}?", f"Which branch had the highest sales on {start_date}?"]
            }

    # 5. BRANCH / STORE SALES (e.g. "least performed 5 future stores on 23-10-2026", "top branches", etc.)
    if any(k in q_low for k in ['branch', 'branches', 'store', 'stores', 'location', 'locations', 'highest store', 'top branch', 'least performed', 'least performing', 'lowest store', 'worst store', 'bottom store']):
        store_type_filter = ""
        store_type_desc = "branches"
        if 'future' in q_low:
            store_type_filter = "AND upper(coalesce(bm.branch_name, s.branch)) LIKE '%FUTURE%'"
            store_type_desc = "Future stores"
        elif 'care' in q_low:
            store_type_filter = "AND upper(coalesce(bm.branch_name, s.branch)) LIKE '%CARE%'"
            store_type_desc = "Care stores"

        order_clause = "ORDER BY revenue ASC" if is_least else "ORDER BY revenue DESC"
        having_clause = "HAVING revenue > 0" if is_least else ""
        rank_word = f"least performing {store_type_desc[:-1] if store_type_desc.endswith('s') else store_type_desc}" if is_least else f"top performing {store_type_desc[:-1] if store_type_desc.endswith('s') else store_type_desc}"
        card_label = f"Lowest {store_type_desc[:-1] if store_type_desc.endswith('s') else store_type_desc}" if is_least else f"Top {store_type_desc[:-1] if store_type_desc.endswith('s') else store_type_desc}"
        card_color = "#ef4444" if is_least else "#4f46e5"

        sql = f"""
            SELECT coalesce(bm.branch_name, s.branch) as branch_name,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as units
            FROM azure_sales_report s
            LEFT JOIN branch_master bm ON bm.code = s.branch
            WHERE {date_filter}
              AND s.branch NOT IN ('SMC', '3GH')
              {store_type_filter}
            GROUP BY branch_name
            {having_clause}
            {order_clause}
            LIMIT {limit}
        """
        rows = run_sql(sql)
        if rows:
            top1 = rows[0]
            ans = f"On **{date_label}**, the {rank_word} was **{top1['branch_name']}**, recording **{format_inr(top1['revenue'])}** in sales ({format_units(top1['units'])} units sold)."
            cards = [
                {"label": card_label, "value": top1['branch_name'], "color": card_color},
                {"label": "Branch Revenue", "value": format_inr(top1['revenue']), "color": "#059669"},
                {"label": "Units Sold", "value": format_units(top1['units']), "color": "#2563eb"}
            ]
            table = {
                "headers": ["Store Branch", "Revenue", "Units Sold"],
                "rows": [[r['branch_name'], format_inr_exact(r['revenue']), format_units(r['units'])] for r in rows]
            }
            return {
                "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                "suggestions": [f"Top {limit} {store_type_desc} on {start_date}", f"What was the total sale on {start_date}?", f"Which product was most sold on {start_date}?"]
            }

    # 6. TOTAL SALE ON A SPECIFIC DATE OR MONTH (e.g. "what was the sale on a specific date")
    sql = f"""
        SELECT 
            sumIf(toFloat64(s.sold_price) * toInt64(s.qty), s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME') as retail_sales,
            sumIf(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty)), s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME') as retail_units,
            count(DISTINCT if(s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME' AND s.sold_price > 0 AND s.invoice_no NOT LIKE '%-SR-%', s.invoice_no, null)) as retail_invoices,
            count(DISTINCT if(s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME', s.branch, null)) as retail_branches,
            sumIf(toFloat64(s.sold_price) * toInt64(s.qty), s.branch IN ('SMC', '3GH') OR coalesce(im.product, '') = 'SCHEME') as internal_schemes_demo,
            sum(toFloat64(s.sold_price) * toInt64(s.qty)) as total_sales,
            sum(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty))) as total_units,
            count(DISTINCT if(s.sold_price > 0 AND s.invoice_no NOT LIKE '%-SR-%', s.invoice_no, null)) as total_invoices
        FROM azure_sales_report s
        LEFT JOIN item_master im ON im.item_code = s.item_code
        WHERE {date_filter}
    """
    rows = run_sql(sql)
    if rows and (rows[0].get('retail_sales') is not None or rows[0].get('total_sales') is not None):
        r = rows[0]
        retail_sales    = float(r.get('retail_sales') or 0)
        retail_units    = int(float(r.get('retail_units') or 0))
        retail_inv      = int(float(r.get('retail_invoices') or 0))
        retail_branches = int(float(r.get('retail_branches') or 0))
        internal_amt    = float(r.get('internal_schemes_demo') or 0)
        gross_sales     = float(r.get('total_sales') or 0)

        # Prefer retail_sales when available, fallback to total_sales
        main_sales = retail_sales if retail_sales > 0 else gross_sales
        main_units = retail_units if retail_sales > 0 else int(float(r.get('total_units') or 0))
        main_inv   = retail_inv if retail_sales > 0 else int(float(r.get('total_invoices') or 0))

        # Check if user requested a comparison with previous year
        if is_compare and prev_date_filter:
            prev_sql = f"""
                SELECT 
                    sumIf(toFloat64(s.sold_price) * toInt64(s.qty), s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME') as retail_sales,
                    sumIf(if(s.sold_price < 0 OR s.invoice_no LIKE '%-SR-%', -toInt64(s.qty), toInt64(s.qty)), s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME') as retail_units,
                    count(DISTINCT if(s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME' AND s.sold_price > 0 AND s.invoice_no NOT LIKE '%-SR-%', s.invoice_no, null)) as retail_invoices,
                    count(DISTINCT if(s.branch NOT IN ('SMC', '3GH') AND coalesce(im.product, '') != 'SCHEME', s.branch, null)) as retail_branches
                FROM azure_sales_report s
                LEFT JOIN item_master im ON im.item_code = s.item_code
                WHERE {prev_date_filter}
            """
            prev_rows = run_sql(prev_sql)
            prev_r = prev_rows[0] if prev_rows else {}
            sales_prev = float(prev_r.get('retail_sales') or 0)
            units_prev = int(float(prev_r.get('retail_units') or 0))
            inv_prev = int(float(prev_r.get('retail_invoices') or 0))
            branches_prev = int(float(prev_r.get('retail_branches') or 0))

            diff_rev = main_sales - sales_prev
            pct_rev = (diff_rev / sales_prev * 100) if sales_prev > 0 else 0
            diff_units = main_units - units_prev
            pct_units = (diff_units / units_prev * 100) if units_prev > 0 else 0

            trend_r = f"{format_inr(diff_rev)} ({pct_rev:+.1f}%)"
            trend_u = f"{diff_units:+d} ({pct_units:+.1f}%)"
            growth_word = "growth" if diff_rev >= 0 else "decline"
            r_color = "#059669" if diff_rev >= 0 else "#ef4444"
            u_color = "#059669" if diff_units >= 0 else "#ef4444"

            ans = (
                f"On **{date_label}**, **Retail Store Net Sales** were **{format_inr(main_sales)}** ({format_inr_exact(main_sales)} across {retail_branches} stores), "
                f"compared to **{format_inr(sales_prev)}** ({format_inr_exact(sales_prev)} across {branches_prev} stores) "
                f"on **{prev_date_label}** of previous year (**{trend_r} revenue {growth_word}**, {trend_u} units)."
            )
            cards = [
                {"label": f"{date_label} Sales", "value": format_inr(main_sales), "color": "#2563eb"},
                {"label": f"{prev_date_label} Sales", "value": format_inr(sales_prev), "color": "#6b7280"},
                {"label": "Revenue Growth (YoY)", "value": trend_r, "color": r_color},
                {"label": "Unit Growth (YoY)", "value": trend_u, "color": u_color}
            ]
            table = {
                "headers": ["Metric", date_label, prev_date_label, "YoY Variance"],
                "rows": [
                    ["Retail Store Sales", format_inr_exact(main_sales), format_inr_exact(sales_prev), trend_r],
                    ["Total Units Sold", f"{main_units:,} units", f"{units_prev:,} units", trend_u],
                    ["Customer Invoices", f"{main_inv:,}", f"{inv_prev:,}", f"{main_inv - inv_prev:+d}"],
                    ["Active Branches", f"{retail_branches}", f"{branches_prev}", f"{retail_branches - branches_prev:+d}"]
                ]
            }
            return {
                "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                "suggestions": [
                    f"Which product was most sold on {start_date}?",
                    f"How much TV was sold on {start_date}?",
                    f"Top branches on {start_date}"
                ]
            }

        # Get top product on this date for added insight
        p_sql = f"""
            SELECT if({PROD_EXPR} = '', 'Other', {PROD_EXPR}) as product,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND s.branch NOT IN ('SMC', '3GH')
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'D SPARE', 'SPARE', 'DEMO', 'DEMO ACCESSORIES')
            GROUP BY product
            ORDER BY revenue DESC
            LIMIT 1
        """
        p_rows = run_sql(p_sql)
        p_extra = ""
        if p_rows and p_rows[0].get('product'):
            p_extra = f" The leading retail category was **{p_rows[0]['product']}** with **{format_inr(p_rows[0]['revenue'])}**."

        reconcile_note = ""
        if internal_amt > 0:
            reconcile_note = f" *(Corporate Gross Billed including HQ demo allocations & scheme vouchers: {format_inr(gross_sales)})*"

        ans = f"On **{date_label}**, **Retail Store Net Sales** were **{format_inr(main_sales)}** ({format_inr_exact(main_sales)}) across **{retail_branches} branches** with **{format_units(main_units)} units** sold across **{format_units(main_inv)} customer invoices**.{p_extra}{reconcile_note}"
        cards = [
            {"label": "Retail Store Sales", "value": format_inr(main_sales), "color": "#059669"},
            {"label": "Units Sold", "value": format_units(main_units), "color": "#2563eb"},
            {"label": "Invoices", "value": format_units(main_inv), "color": "#7c3aed"},
            {"label": "Active Stores", "value": format_units(retail_branches), "color": "#d97706"}
        ]
        return {
            "answer": ans, "sql": sql.strip(), "cards": cards,
            "suggestions": [
                f"Which product was most sold on {start_date}?",
                f"How much TV was sold on {start_date}?",
                f"How much Mobile was sold on {start_date}?",
                f"Top branches on {start_date}"
            ]
        }

    # Fallback response
    return {
        "answer": f"I analyzed your question: *\"{question}\"*, but couldn't find matching records in ClickHouse. Try asking with a date (e.g. `2026-08-14`), a product (e.g. `TV`, `Mobile`, `Laptop`), or a branch name.",
        "sql": "",
        "cards": [],
        "suggestions": [
            "What was the sale on 2026-08-14?",
            "Which product was most sold on 2026-08-14?",
            "How much TV was sold on 2026-08-14?",
            "What was our top performing campaign?"
        ]
    }

def ask_ai(question, history=None):
    """
    Main entry point: uses Gemini if GEMINI_API_KEY is available,
    otherwise uses the built-in ClickHouse NLP engine.
    """
    # Follow-up such as "give as an excel report": re-run the previous user question so its Excel download is returned
    _ql = (question or '').lower()
    if (history and len(_ql.split()) <= 10 and re.search(r'\b(excel|xlsx|spreadsheet|download|export)\b', _ql)
            and not re.search(r'\b(store|branch|future|sale|sales|campaign)\b', _ql)):
        _prev = [h.get('content', '') for h in history if h.get('role') == 'user'
                 and not re.search(r'\b(excel|xlsx|spreadsheet|download|export)\b', (h.get('content') or '').lower())]
        if _prev:
            _res = answer_with_nlp(_prev[-1])
            if isinstance(_res, dict) and _res.get('download'):
                return _res
    gemini_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if gemini_key:
        try:
            return ask_gemini(question, gemini_key, history)
        except Exception as e:
            print(f"[Gemini API fallback to deterministic engine] {e}")

    return answer_with_nlp(question)

def ask_gemini(question, api_key, history=None):
    """
    Calls Google Gemini to generate ClickHouse SQL, executes it, and synthesizes the answer.
    """
    sys_prompt = """
    You are an expert ClickHouse Data Analyst for a retail electronics company (MyG).
    You generate ONLY valid, read-only ClickHouse SQL queries based on user questions.
    
    ClickHouse Schema:
    1. Table: azure_sales_report (alias s)
       Columns: date (Date/DateTime), invoice_no, branch, item_code, qty, sold_price (String/Float), discount, taxable
    2. Table: item_master (alias im)
       Columns: item_code, product (e.g. TV, MOBILE, LAPTOP, REFRIGERATORS, WASHING MACHINES, AIR CONDITIONER), brand, category, item_name
    3. Table: branch_master (alias bm)
       Columns: code, branch_name
    4. Table: campaign_dashboard_campaigns (source_db = 'root')
       Columns: id, campaign_name, type, start_date, end_date, target_size, purchase_count, purchase_value, roi, conversion_rate
       
    Rules:
    - Return ONLY a JSON object: {"sql": "SELECT ..."}
    - Always use toDate(s.date) or toDate(date) for date comparisons
    - Never count 'AC OUTDOOR' or 'SCHEME' in products
    - For revenue use: sum(toFloat64(s.sold_price) * toInt64(s.qty))
    - Limit results to at most 10 rows
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": sys_prompt + "\n\nUser Question: " + question}]}
        ],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=12) as resp:
        res = json.loads(resp.read().decode('utf-8'))
        raw_text = res['candidates'][0]['content']['parts'][0]['text']
        parsed = json.loads(raw_text)
        sql = parsed.get('sql')
        
    if not sql:
        return answer_with_nlp(question)
        
    data = run_sql(sql)
    
    # Send data back to Gemini for rich answer synthesis
    synth_prompt = f"User asked: {question}\nExecuted SQL: {sql}\nClickHouse Data: {json.dumps(data)}\nSummarize this accurately in 1-2 friendly sentences. Format amounts in Indian Rupees (₹Cr, ₹L)."
    synth_payload = {
        "contents": [{"role": "user", "parts": [{"text": synth_prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    req2 = urllib.request.Request(url, data=json.dumps(synth_payload).encode('utf-8'), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req2, timeout=12) as resp2:
        res2 = json.loads(resp2.read().decode('utf-8'))
        answer = res2['candidates'][0]['content']['parts'][0]['text']
        
    return {
        "answer": answer,
        "sql": sql,
        "cards": [],
        "suggestions": ["What was the sale on 2026-08-14?", "Which product was most sold on 2026-08-14?", "How much TV was sold on 2026-08-14?"]
    }
