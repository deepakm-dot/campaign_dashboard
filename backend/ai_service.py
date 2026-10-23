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

PRODUCT_SYNONYMS = {
    'TV': ['tv', 'television', 'televisions', 'led tv', 'smart tv', 'oled'],
    'MOBILE': ['mobile', 'mobiles', 'smartphone', 'smartphones', 'phone', 'phones', 'handset'],
    'LAPTOP': ['laptop', 'laptops', 'notebook', 'pc', 'computer'],
    'REFRIGERATORS': ['refrigerator', 'refrigerators', 'fridge', 'fridges', 'deep freezer'],
    'WASHING MACHINES': ['washing machine', 'washing machines', 'washer', 'washers', 'wm'],
    'AIR CONDITIONER': ['ac', 'air conditioner', 'airconditioner', 'air conditioners', 'cooling'],
    'SMART WATCH': ['smart watch', 'smartwatch', 'smart watches', 'wearable watch'],
    'EAR WEARABLES': ['earbuds', 'earphone', 'earphones', 'tws', 'airpods', 'headphone', 'headphones'],
    'AUDIO': ['audio', 'soundbar', 'speaker', 'speakers', 'home theatre'],
    'SMALL APPLIANCES': ['small appliance', 'small appliances', 'mixer', 'grinder', 'iron box', 'kettle']
}

def extract_product(text):
    t = text.lower()
    for prod_key, syns in PRODUCT_SYNONYMS.items():
        for syn in syns:
            if re.search(r'\b' + re.escape(syn) + r'\b', t):
                return prod_key
    return None

BRANDS = [
    'samsung', 'apple', 'lg', 'sony', 'xiaomi', 'mi', 'redmi', 'vivo', 'oppo',
    'oneplus', 'realme', 'motorola', 'whirlpool', 'haier', 'godrej', 'voltas',
    'lloyd', 'daikin', 'panasonic', 'dell', 'hp', 'lenovo', 'asus', 'acer',
    'boat', 'noise', 'fire-boltt', 'impex', 'philips', 'preethi', 'bajaj'
]

def extract_brand(text):
    t = text.lower()
    for b in BRANDS:
        if re.search(r'\b' + re.escape(b) + r'\b', t):
            if b in ('mi', 'redmi'): return 'XIAOMI'
            return b.upper()
    return None

def answer_with_nlp(question):
    """
    Deterministic semantic NLP engine that understands sales, products,
    brands, branches, and campaigns directly from ClickHouse.
    """
    q_low = question.lower().strip()
    
    start_date, end_date, date_label, is_month = extract_dates(question)
    product = extract_product(question)
    brand = extract_brand(question)

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
    date_filter_raw = f"toDate(date) = '{start_date}'" if start_date == end_date else f"toDate(date) >= '{start_date}' AND toDate(date) <= '{end_date}'"

    # 1. CAMPAIGN QUERIES
    if any(k in q_low for k in ['campaign', 'campaigns', 'group', 'roi', 'attribution', 'channel']):
        if 'top' in q_low or 'best' in q_low or 'highest' in q_low:
            sql = """
                SELECT campaign_name, type, start_date, target_size, purchase_count, 
                       purchase_value, roi, conversion_rate
                FROM campaign_dashboard_campaigns
                WHERE source_db = 'root' AND purchase_value > 0
                ORDER BY purchase_value DESC
                LIMIT 5
            """
            rows = run_sql(sql)
            if rows:
                top1 = rows[0]
                ans = f"The top performing campaign is **{top1['campaign_name']}** ({top1['type']}) with **{format_inr(top1['purchase_value'])}** in revenue, **{format_units(top1['purchase_count'])}** verified customer purchases, and an ROI of **{float(top1.get('roi') or 0):.0f}x**."
                cards = [
                    {"label": "Top Campaign", "value": top1['campaign_name'], "color": "#4f46e5"},
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

    # 2. SPECIFIC PRODUCT + BRAND SALES (e.g. "how much samsung tv was sold on date")
    if product and brand:
        sql = f"""
            SELECT coalesce(im.brand, '{brand}') as brand,
                   coalesce(im.product, '{product}') as product,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(toInt64(s.qty)) as units
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND upper(im.brand) = '{brand}'
              AND upper(im.product) LIKE '%{product}%'
            GROUP BY brand, product
        """
        rows = run_sql(sql)
        rev = rows[0]['revenue'] if rows else 0
        units = rows[0]['units'] if rows else 0
        ans = f"On **{date_label}**, total **{brand} {product}** sales were **{format_inr(rev)}** ({format_inr_exact(rev)}) with **{format_units(units)} units** sold."
        cards = [
            {"label": f"{brand} {product} Revenue", "value": format_inr(rev), "color": "#059669"},
            {"label": "Units Sold", "value": format_units(units), "color": "#2563eb"},
            {"label": "Period", "value": date_label, "color": "#7c3aed"}
        ]
        return {
            "answer": ans, "sql": sql.strip(), "cards": cards,
            "suggestions": [f"Top brands for {product} on {start_date}", f"Total {product} sales on {start_date}", f"What was the overall sale on {start_date}?"]
        }

    # 3. SPECIFIC PRODUCT SALES (e.g. "how much tv was sold on 2026-08-14")
    if product:
        sql = f"""
            SELECT coalesce(im.product, '{product}') as product,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(toInt64(s.qty)) as units
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND upper(im.product) LIKE '%{product}%'
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR')
            GROUP BY product
        """
        rows = run_sql(sql)
        rev = rows[0]['revenue'] if rows else 0
        units = rows[0]['units'] if rows else 0
        
        # Also query top 3 brands for this product
        b_sql = f"""
            SELECT coalesce(im.brand, 'Other') as brand,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(toInt64(s.qty)) as units
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND upper(im.product) LIKE '%{product}%'
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR')
            GROUP BY brand
            ORDER BY revenue DESC
            LIMIT 5
        """
        b_rows = run_sql(b_sql)
        top_brand_txt = ""
        if b_rows:
            top_brand_txt = f" Top brand was **{b_rows[0]['brand']}** with **{format_inr(b_rows[0]['revenue'])}** ({format_units(b_rows[0]['units'])} units)."

        ans = f"On **{date_label}**, total **{product}** sales were **{format_inr(rev)}** ({format_inr_exact(rev)}) with **{format_units(units)} units** sold across all branches.{top_brand_txt}"
        cards = [
            {"label": f"Total {product} Revenue", "value": format_inr(rev), "color": "#059669"},
            {"label": "Units Sold", "value": format_units(units), "color": "#2563eb"},
            {"label": "Date", "value": date_label, "color": "#7c3aed"}
        ]
        table = None
        if b_rows:
            table = {
                "headers": ["Brand", "Revenue", "Units Sold"],
                "rows": [[r['brand'], format_inr_exact(r['revenue']), format_units(r['units'])] for r in b_rows]
            }
        return {
            "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
            "suggestions": [f"Which product was most sold on {start_date}?", f"What was the total sale on {start_date}?", f"Top branches for {product} on {start_date}"]
        }

    # 4. MOST SOLD PRODUCT (e.g. "which product was most sold on this date")
    if any(k in q_low for k in ['most sold', 'top product', 'top selling product', 'highest sold product', 'product breakdown']):
        sql = f"""
            SELECT coalesce(im.product, 'Other') as product,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(toInt64(s.qty)) as units
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'D SPARE', 'SPARE', 'FIXED ASSETS')
            GROUP BY product
            ORDER BY revenue DESC
            LIMIT 5
        """
        rows = run_sql(sql)
        if rows:
            top1 = rows[0]
            ans = f"On **{date_label}**, the most sold product by revenue was **{top1['product']}**, generating **{format_inr(top1['revenue'])}** ({format_inr_exact(top1['revenue'])}) with **{format_units(top1['units'])} units** sold."
            cards = [
                {"label": "Top Product", "value": top1['product'], "color": "#4f46e5"},
                {"label": "Top Product Revenue", "value": format_inr(top1['revenue']), "color": "#059669"},
                {"label": "Top Product Units", "value": format_units(top1['units']), "color": "#2563eb"},
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

    # 5. BRANCH / STORE SALES
    if any(k in q_low for k in ['branch', 'store', 'location', 'highest store', 'top branch']):
        sql = f"""
            SELECT coalesce(bm.branch_name, s.branch) as branch_name,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue,
                   sum(toInt64(s.qty)) as units
            FROM azure_sales_report s
            LEFT JOIN branch_master bm ON bm.code = s.branch
            WHERE {date_filter}
            GROUP BY branch_name
            ORDER BY revenue DESC
            LIMIT 5
        """
        rows = run_sql(sql)
        if rows:
            top1 = rows[0]
            ans = f"On **{date_label}**, the top performing branch was **{top1['branch_name']}**, achieving **{format_inr(top1['revenue'])}** in sales ({format_units(top1['units'])} units sold)."
            cards = [
                {"label": "Top Branch", "value": top1['branch_name'], "color": "#4f46e5"},
                {"label": "Branch Revenue", "value": format_inr(top1['revenue']), "color": "#059669"},
                {"label": "Units Sold", "value": format_units(top1['units']), "color": "#2563eb"}
            ]
            table = {
                "headers": ["Store Branch", "Revenue", "Units Sold"],
                "rows": [[r['branch_name'], format_inr_exact(r['revenue']), format_units(r['units'])] for r in rows]
            }
            return {
                "answer": ans, "sql": sql.strip(), "cards": cards, "table": table,
                "suggestions": [f"Which product was most sold on {start_date}?", f"What was the total sale on {start_date}?", "Show top campaigns"]
            }

    # 6. TOTAL SALE ON A SPECIFIC DATE OR MONTH (e.g. "what was the sale on a specific date")
    sql = f"""
        SELECT sum(toFloat64(sold_price) * toInt64(qty)) as total_sales,
               sum(toInt64(qty)) as total_units,
               count(DISTINCT invoice_no) as total_invoices
        FROM azure_sales_report
        WHERE {date_filter_raw}
    """
    rows = run_sql(sql)
    if rows and rows[0].get('total_sales') is not None:
        r = rows[0]
        total_sales = float(r.get('total_sales') or 0)
        total_units = int(r.get('total_units') or 0)
        total_inv   = int(r.get('total_invoices') or 0)

        # Get top product on this date for added insight
        p_sql = f"""
            SELECT coalesce(im.product, 'Other') as product,
                   sum(toFloat64(s.sold_price) * toInt64(s.qty)) as revenue
            FROM azure_sales_report s
            LEFT JOIN item_master im ON im.item_code = s.item_code
            WHERE {date_filter}
              AND coalesce(im.product, '') NOT IN ('SCHEME', 'AC OUTDOOR', 'D SPARE', 'SPARE')
            GROUP BY product
            ORDER BY revenue DESC
            LIMIT 1
        """
        p_rows = run_sql(p_sql)
        p_extra = ""
        if p_rows and p_rows[0].get('product'):
            p_extra = f" The leading category was **{p_rows[0]['product']}** with **{format_inr(p_rows[0]['revenue'])}**."

        ans = f"On **{date_label}**, total sales were **{format_inr(total_sales)}** ({format_inr_exact(total_sales)}) with **{format_units(total_units)} units** sold across **{format_units(total_inv)} invoices**.{p_extra}"
        cards = [
            {"label": "Total Sales", "value": format_inr(total_sales), "color": "#059669"},
            {"label": "Units Sold", "value": format_units(total_units), "color": "#2563eb"},
            {"label": "Total Invoices", "value": format_units(total_inv), "color": "#7c3aed"},
            {"label": "Date", "value": date_label, "color": "#d97706"}
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
