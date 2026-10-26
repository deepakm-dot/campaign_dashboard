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

_BRANCH_MAP_CACHE = None

def get_branch_map():
    global _BRANCH_MAP_CACHE
    if _BRANCH_MAP_CACHE is not None:
        return _BRANCH_MAP_CACHE
    try:
        rows = run_sql("SELECT code, branch_name FROM branch_master")
        b_map = {}
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

def answer_with_nlp(question):
    """
    Deterministic semantic NLP engine that understands sales, products,
    brands, branches, and campaigns directly from ClickHouse.
    """
    q_low = question.lower().strip()
    
    start_date, end_date, date_label, is_month = extract_dates(question)
    product, item_term, display_name = extract_product_and_item(question)
    brand = extract_brand(question)

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
        if 'today' in q_low or 'yesterday' in q_low or 'recent' in q_low:
            start_date = '2026-10-22'
            end_date = '2026-10-22'
            date_label = '22 Oct 2026'
        else:
            start_date = '2026-08-14'
            end_date = '2026-08-14'
            date_label = '14 Aug 2026 (Benchmark)'

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

    # 1b. PRODUCT RANKING - "which product sold the most/least on <date>" (all stores or one store)
    rank_intent = bool(re.search(r'\b(most|least|highest|lowest|top|best|worst|bottom|selling|slowest|fastest)\b', q_low)) \
        and bool(re.search(r'\b(products?|items?|categor(?:y|ies)|models?)\b', q_low))
    if (rank_intent or any(k in q_low for k in ['product breakdown', 'sold the most', 'sold most', 'most sold', 'best selling', 'top selling'])) \
            and not (product or item_term) \
            and (bool(target_branch_code) or not any(k in q_low for k in ['store', 'stores', 'branches', 'branch'])):
        by_revenue = any(k in q_low for k in ['revenue', 'sales value', 'amount', 'value', 'turnover', 'worth'])
        excluded = ("'SCHEME','AC OUTDOOR','D SPARE','SPARE','GDP-SPARE','FIXED ASSETS','DEMO','DEMO ACCESSORIES',"
                    "'STATIONERY ITEMS','GIFT ITEMS','OFFER KIT','FOC','SERVICE','SERVICE CHARGES','OSG WARRANTY',"
                    "'CARE PLUS','LG AMC','GDOT CARE','TOTAL SECURITY','MOBILE ANTIVIRUS','CEGI'")
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
                item_cond = "(upper(im.product) = 'WASHING MACHINES' OR s.item_code LIKE 'WM%') AND coalesce(im.product, '') NOT IN ('SCHEME', 'DEMO', 'DEMO ACCESSORIES')"
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
                SELECT coalesce(im.brand, 'Other') as brand,
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
            SELECT coalesce(im.product, 'Other') as product,
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
            SELECT coalesce(im.product, 'Other') as product,
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
            SELECT coalesce(im.product, 'Other') as product,
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
