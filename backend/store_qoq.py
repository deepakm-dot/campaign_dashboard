"""Same-quarter year-on-year (e.g. JAS 2026 vs JAS 2025), product-wise analysis for a single store from its real opening date,
with declining products. Quarter-by-quarter trend is shown for context."""
import os
import re
import uuid
import datetime as dt
from collections import defaultdict

from store_review import (PROD, QTY, REV, _d, _f, _pct, _fp, _qstart, _qend, _quarter_label, _first_sales)

MIN_BASE = 30  # ignore percentage moves on tiny bases (units)


def store_qoq(code, name, latest_date_str):
    import ai_service as A
    q = lambda sql, t=120: A.ch_query(sql, timeout=t, quote64=True) or []
    inr = A.format_inr
    latest = _d(latest_date_str)
    first = _first_sales(A.ch_query).get(code)
    if not first:
        return {"answer": f"No sales found for {name}.", "cards": [], "table": None, "suggestions": []}
    base_filter = "coalesce(im.product, '') != 'SCHEME' AND coalesce(im.item_group, '') != 'SCHEME'"

    # quarter x category (units net of returns, revenue) + units on lines priced under Rs 1
    rows = q(f"""SELECT toString(toStartOfQuarter(toDate(s.date))) AS qs, {PROD} AS grp, sum({QTY}) AS u, sum({REV}) AS r,
                        sumIf({QTY}, s.sold_price >= 0 AND s.sold_price < 1 AND s.invoice_no NOT LIKE '%-SR-%') AS zu
                 FROM azure_sales_report s LEFT JOIN item_master im ON im.item_code = s.item_code
                 WHERE s.branch = '{code}' AND toDate(s.date) >= '{first}' AND {base_filter} GROUP BY qs, grp""")
    data = defaultdict(lambda: [0, 0.0])
    zero = defaultdict(int)
    for r in rows:
        k = (_d(r['qs']), r['grp'])
        data[k][0] += int(_f(r['u'])); data[k][1] += _f(r['r']); zero[k] += int(_f(r['zu']))
    all_q = sorted({k[0] for k in data})
    comp = [k for k in all_q if _qend(k) <= latest]
    part = [k for k in all_q if _qend(k) > latest]
    if len(comp) < 2:
        return {"answer": f"{name} has fewer than two complete quarters of data since {first:%d-%b-%Y}.", "cards": [], "table": None, "suggestions": []}
    cats = sorted({k[1] for k in data})

    def U(c, k): return data.get((k, c), [0, 0.0])[0]
    def R(c, k): return data.get((k, c), [0, 0.0])[1]
    tot_u = {k: sum(U(c, k) for c in cats) for k in all_q}
    tot_r = {k: sum(R(c, k) for c in cats) for k in all_q}

    # mobile brand x quarter
    brows = q(f"""SELECT toString(toStartOfQuarter(toDate(s.date))) AS qs, coalesce(im.brand,'Other') AS b, sum({QTY}) AS u, sum({REV}) AS r
                  FROM azure_sales_report s LEFT JOIN item_master im ON im.item_code = s.item_code
                  WHERE s.branch = '{code}' AND toDate(s.date) >= '{first}' AND {PROD} = 'MOBILE' AND s.item_code NOT LIKE 'SRV%' GROUP BY qs, b""")
    bd = defaultdict(lambda: [0, 0.0])
    for r in brows:
        bd[(_d(r['qs']), r['b'])][0] += int(_f(r['u'])); bd[(_d(r['qs']), r['b'])][1] += _f(r['r'])

    # same-quarter pairs: (current, year-ago). Fall back to previous quarter only if the store has no year-ago quarter yet.
    pairs = [(comp[i], comp[i - 4]) for i in range(4, len(comp))]
    yoy_mode = bool(pairs)
    if not pairs:
        pairs = [(comp[-1], comp[-2])]
    L, B = pairs[-1]
    labL, labB = _quarter_label(L), _quarter_label(B)
    basis = 'year on year (same quarter)' if yoy_mode else 'quarter on quarter (no year-ago quarter yet)'
    brands = sorted({k[1] for k in bd}, key=lambda b: -bd.get((L, b), [0, 0])[0])

    # in-progress quarter to date vs the same dates last year
    ytd = None
    if part:
        ps = part[-1]; pe = latest; ls = dt.date(ps.year - 1, ps.month, ps.day); le = dt.date(pe.year - 1, pe.month, min(pe.day, 28 if pe.month == 2 else pe.day))
        if first <= ls:
            yr = q(f"""SELECT {PROD} AS grp, sumIf({QTY}, toDate(s.date) BETWEEN '{ps}' AND '{pe}') AS cu,
                              sumIf({QTY}, toDate(s.date) BETWEEN '{ls}' AND '{le}') AS pu
                       FROM azure_sales_report s LEFT JOIN item_master im ON im.item_code = s.item_code
                       WHERE s.branch = '{code}' AND toDate(s.date) BETWEEN '{ls}' AND '{pe}' AND {base_filter} GROUP BY grp""")
            ytd = {'cur': (ps, pe), 'prev': (ls, le), 'rows': {r['grp']: (int(_f(r['cu'])), int(_f(r['pu']))) for r in yr}}

    # ---- per-category comparison for every pair ----
    focus = [c for c in cats if c in A.FOCUS_CATS or c in A.KEY_CATS]
    mark = lambda c: '★ ' if c in A.KEY_CATS else ''

    def cmp_(c, cur, base):
        uc, ub, rc, rb = U(c, cur), U(c, base), R(c, cur), R(c, base)
        pu = _pct(uc, ub) if ub >= MIN_BASE else None
        pr = _pct(rc, rb) if rb > 0 and ub >= MIN_BASE else None
        status = 'Small base' if pu is None else ('Declining' if pu < 0 else 'Growing')
        return {'uc': uc, 'ub': ub, 'du': uc - ub, 'pu': pu, 'rc': rc, 'rb': rb, 'dr': rc - rb, 'pr': pr, 'status': status}
    P2 = {pr_: {c: cmp_(c, pr_[0], pr_[1]) for c in focus} for pr_ in pairs}
    prim = P2[(L, B)]
    order = sorted(focus, key=lambda c: (0 if c in A.KEY_CATS else 1, -prim[c]['uc']))
    declining = sorted([c for c in focus if prim[c]['status'] == 'Declining'], key=lambda c: prim[c]['du'])
    rev_down = sorted([c for c in focus if prim[c]['status'] != 'Small base' and prim[c]['dr'] < 0 and prim[c]['status'] != 'Declining'], key=lambda c: prim[c]['dr'])
    growing = sorted([c for c in focus if prim[c]['status'] == 'Growing'], key=lambda c: -prim[c]['du'])
    persist = []
    if len(pairs) >= 2:
        persist = [c for c in declining if all(P2[p][c]['status'] == 'Declining' for p in pairs)]

    def line(c):
        i = prim[c]
        extra = ''
        if i['pr'] is not None and i['du'] < 0 and i['dr'] > 0:
            extra = ' - fewer units but higher revenue (higher selling price / mix)'
        elif i['pr'] is not None and i['du'] < 0 and i['dr'] < 0:
            extra = ' - both units and revenue are down'
        return (f"{mark(c)}{c} {i['ub']:,} -> {i['uc']:,} units ({i['du']:+,}, {_fp(i['uc'], i['ub'])}); "
                f"revenue {inr(i['rb'])} -> {inr(i['rc'])} ({_fp(i['rc'], i['rb'])}){extra}")

    # ---- chat answer ----
    months_between = (B.year - first.year) * 12 + B.month - first.month
    ans = [f"**{labL} vs {labB} - product-wise comparison: {name}** ({basis}). Store opened {first:%d-%b-%Y}; data to {latest:%d-%b-%Y}. "
           f"Merchandise only (services, warranties, gifts, stationery, spares, demo excluded); units net of returns."]
    tu, tb = tot_u[L], tot_u[B]; tr, trb = tot_r[L], tot_r[B]
    ans.append(f"\n**Store total, {labL} vs {labB}:** units {tb:,} -> {tu:,} ({_fp(tu, tb)}); revenue {inr(trb)} -> {inr(tr)} ({_fp(tr, trb)}).")
    if yoy_mode and months_between < 6:
        ans.append(f"Caution: {labB} was only months {max(months_between, 0) + 1}-{max(months_between, 0) + 3} of this store's trading (opened {first:%d-%b-%Y}), so that base was still ramping up and growth is flattered.")
    ans.append("\n**Same-quarter comparison for every quarter that has a year-ago quarter**")
    for cur, base in pairs:
        ans.append(f"- {_quarter_label(cur)} vs {_quarter_label(base)}: revenue {inr(tot_r[base])} -> {inr(tot_r[cur])} ({_fp(tot_r[cur], tot_r[base])}); units {tot_u[base]:,} -> {tot_u[cur]:,} ({_fp(tot_u[cur], tot_u[base])})" +
                   (" - base is the store's launch quarter (launch-period volumes, especially low-value items such as crockery and small appliances, were unusually high), so treat this comparison with care" if base == _qstart(first) else ""))
    ans.append("\n**Quarter-by-quarter revenue (context):** " + "; ".join(f"{_quarter_label(k)} {inr(tot_r[k])}" for k in comp) +
               (f"; {_quarter_label(part[-1])} so far {inr(tot_r[part[-1]])}." if part else "."))

    ans.append(f"\n**Declining products - {labL} vs {labB}** (units fell; ★ = key product; categories with under {MIN_BASE} units in {labB} are ignored)")
    if declining:
        ans.extend(f"- {line(c)}" for c in declining[:12])
    else:
        ans.append(f"No product sold fewer units in {labL} than in {labB}.")
    if rev_down:
        ans.append(f"Units up but revenue down: " + "; ".join(f"{mark(c)}{c} units {prim[c]['ub']:,} -> {prim[c]['uc']:,}, revenue {_fp(prim[c]['rc'], prim[c]['rb'])}" for c in rev_down[:6]) + ".")
    if len(pairs) >= 2:
        if persist:
            ans.append(f"Declining in every same-quarter comparison ({', '.join(_quarter_label(p[0]) + ' vs ' + _quarter_label(p[1]) for p in pairs)}): " + ", ".join(mark(c) + c for c in persist) + ".")
        for p in pairs[:-1]:
            dn = sorted([c for c in focus if P2[p][c]['status'] == 'Declining'], key=lambda c: P2[p][c]['du'])
            if dn:
                ans.append(f"Also declining in {_quarter_label(p[0])} vs {_quarter_label(p[1])}: " + "; ".join(f"{mark(c)}{c} {P2[p][c]['ub']:,} -> {P2[p][c]['uc']:,} ({_fp(P2[p][c]['uc'], P2[p][c]['ub'])})" for c in dn[:8]) + ".")
    if growing:
        ans.append(f"\n**Growing products - {labL} vs {labB}** (top by extra units): " + "; ".join(f"{mark(c)}{c} {prim[c]['ub']:,} -> {prim[c]['uc']:,} ({prim[c]['du']:+,}, {_fp(prim[c]['uc'], prim[c]['ub'])})" for c in growing[:6]) + ".")
    if brands:
        bl = []
        for b in brands[:8]:
            ub_, uc_ = bd.get((B, b), [0, 0])[0], bd.get((L, b), [0, 0])[0]
            if ub_ >= MIN_BASE // 2 and uc_ < ub_:
                bl.append((b, ub_, uc_))
        if bl:
            ans.append(f"\n**Mobile brands down, {labL} vs {labB}:** " + "; ".join(f"{b} {a:,} -> {z:,} ({_fp(z, a)})" for b, a, z in sorted(bl, key=lambda x: x[2] - x[1])[:6]) + ".")
    if ytd:
        dn = sorted([(c, a, b) for c, (a, b) in ytd['rows'].items() if c in focus and b >= MIN_BASE and a < b], key=lambda x: x[1] - x[2])[:6]
        if dn:
            ans.append(f"\n**{_quarter_label(part[-1])} so far** ({ytd['cur'][0]:%d-%b} to {ytd['cur'][1]:%d-%b}) vs the same dates last year - declining: " +
                       "; ".join(f"{mark(c)}{c} {b:,} -> {a:,} ({_fp(a, b)})" for c, a, b in dn) + ". Caution: Diwali run-up fell inside these dates in 2025 (20-Oct) but falls on 8-Nov in 2026, so October is not like-for-like.")
    zk = [(c, zero.get((L, c), 0), U(c, L)) for c in A.KEY_CATS if zero.get((L, c), 0)]
    if zk:
        ans.append(f"\n**Data note ({labL} units):** unit counts include lines priced under Rs 1 (free items / exchange intake), as in every other Ask AI answer - " +
                   "; ".join(f"{c} {z:,} of {t:,}" for c, z, t in zk) + ". Revenue is unaffected. The Excel 'Data Notes' sheet shows this for every product and quarter.")
    ans.append("\nThe Excel has the same-quarter comparison for every product and quarter, the full quarter-by-product matrices, brands and data notes.")

    # ---- Excel ----
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = Workbook(); hdr = PatternFill('solid', fgColor='1F2A56'); keyf = PatternFill('solid', fgColor='FFF2CC'); redf = PatternFill('solid', fgColor='F8D7DA')
    red, green = Font(color='C00000', bold=True), Font(color='2E7D32', bold=True)

    def sheet(title, headers, data_rows, num=(), pct=(), delta=(), keycol=None, statuscol=None):
        ws = wb.create_sheet(title) if wb.active.title != 'Sheet' or title != 'Summary' else wb.active
        if ws.title == 'Sheet': ws.title = title
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color='FFFFFF'); c.fill = hdr; c.alignment = Alignment(horizontal='center', wrap_text=True)
        for r_ in data_rows: ws.append(r_)
        for i in range(2, ws.max_row + 1):
            for ci in num: ws.cell(i, ci).number_format = '#,##0'
            for ci in pct: ws.cell(i, ci).number_format = '0.0%'
            for ci in delta:
                v = ws.cell(i, ci).value
                if isinstance(v, (int, float)) and v != 0: ws.cell(i, ci).font = red if v < 0 else green
            if keycol and ws.cell(i, keycol).value in A.KEY_CATS:
                for cc in range(1, len(headers) + 1): ws.cell(i, cc).fill = keyf
            if statuscol and str(ws.cell(i, statuscol).value or '').startswith('Declining'):
                ws.cell(i, statuscol).fill = redf
        for ci, h in enumerate(headers, 1):
            w = max([len(str(h))] + [len(str(ws.cell(i, ci).value or '')) for i in range(2, min(ws.max_row, 80) + 1)])
            ws.column_dimensions[get_column_letter(ci)].width = min(max(w + 2, 11), 40)
        ws.freeze_panes = 'B2'
        return ws

    ql = [_quarter_label(k) for k in comp]
    sheet('Summary', ['Quarter', 'Units', 'Revenue', 'Units vs year-ago %', 'Revenue vs year-ago %', 'Revenue vs previous quarter %', 'Complete?'],
          [[_quarter_label(k), tot_u[k], tot_r[k], _pct(tot_u[k], tot_u[all_q[i - 4]]) if i >= 4 else None, _pct(tot_r[k], tot_r[all_q[i - 4]]) if i >= 4 else None,
            _pct(tot_r[k], tot_r[all_q[i - 1]]) if i else None, 'Yes' if k in comp else 'In progress'] for i, k in enumerate(all_q)], num=(2, 3), pct=(4, 5, 6))

    def pair_sheet(cur, base, info, title):
        hd = ['Product', f'Units {_quarter_label(base)}', f'Units {_quarter_label(cur)}', 'Unit change', 'Unit %',
              f'Revenue {_quarter_label(base)}', f'Revenue {_quarter_label(cur)}', 'Revenue change', 'Revenue %', 'Status']
        body = []
        for c in sorted(focus, key=lambda c: (0 if c in A.KEY_CATS else 1, info[c]['du'])):
            i = info[c]
            body.append([c, i['ub'], i['uc'], i['du'], i['pu'], i['rb'], i['rc'], i['dr'], i['pr'], i['status']])
        sheet(title, hd, body, num=(2, 3, 4, 6, 7, 8), pct=(5, 9), delta=(4, 8), keycol=1, statuscol=10)
    for (cur, base) in reversed(pairs):
        pair_sheet(cur, base, P2[(cur, base)], f'{_quarter_label(cur)} vs {_quarter_label(base)}'[:31])
    sheet('Declining Products', ['Product', f'Units {labB}', f'Units {labL}', 'Unit change', 'Unit %', f'Revenue {labB}', f'Revenue {labL}', 'Revenue change', 'Revenue %', 'Declining in every comparison?'],
          [[c, prim[c]['ub'], prim[c]['uc'], prim[c]['du'], prim[c]['pu'], prim[c]['rb'], prim[c]['rc'], prim[c]['dr'], prim[c]['pr'], ('Yes' if c in persist else ('No' if len(pairs) >= 2 else '-'))]
           for c in declining + rev_down], num=(2, 3, 4, 6, 7, 8), pct=(5, 9), delta=(4, 8), keycol=1)
    sheet('Units by Quarter', ['Product'] + ql,
          [[c] + [U(c, k) for k in comp] for c in order], num=tuple(range(2, 2 + len(ql))), keycol=1)
    sheet('Revenue by Quarter', ['Product'] + ql,
          [[c] + [R(c, k) for k in comp] for c in order], num=tuple(range(2, 2 + len(ql))), keycol=1)
    sheet('All Categories', ['Product'] + [f'Units {x}' for x in ql] + [f'Revenue {x}' for x in ql],
          [[c] + [U(c, k) for k in comp] + [R(c, k) for k in comp] for c in sorted(cats, key=lambda c: -U(c, L))], num=tuple(range(2, 2 + 2 * len(ql))), keycol=1)
    if brands:
        sheet('Mobile Brands by Quarter', ['Brand'] + [f'Units {x}' for x in ql] + [f'Unit change {labB}->{labL}'],
              [[b] + [bd.get((k, b), [0, 0])[0] for k in comp] + [bd.get((L, b), [0, 0])[0] - bd.get((B, b), [0, 0])[0]] for b in brands], num=tuple(range(2, 3 + len(ql))), delta=(2 + len(ql),))
    if ytd:
        sheet(f'{_quarter_label(part[-1])} to date', ['Product', f"Units {ytd['cur'][0]:%d-%b-%y} to {ytd['cur'][1]:%d-%b-%y}", f"Units {ytd['prev'][0]:%d-%b-%y} to {ytd['prev'][1]:%d-%b-%y}", 'Change', '%'],
              [[c, a, b, a - b, _pct(a, b)] for c, (a, b) in sorted(ytd['rows'].items(), key=lambda x: x[1][0] - x[1][1]) if c in focus], num=(2, 3, 4), pct=(5,), delta=(4,), keycol=1)

    wn = sheet('Data Notes', ['Product'] + [f'Rs0-price units {x}' for x in ql] + [f'Total units {x}' for x in ql],
               [[c] + [zero.get((k, c), 0) for k in comp] + [U(c, k) for k in comp] for c in sorted(cats, key=lambda c: -sum(zero.get((k, c), 0) for k in comp)) if any(zero.get((k, c), 0) for k in comp)],
               num=tuple(range(2, 2 + 2 * len(ql))), keycol=1)
    notes = ["DEFINITIONS USED IN THIS REPORT",
             f"Store: {name}; period: {first:%d-%b-%Y} (first trading day, first day with sales of Rs 1 lakh or more) to {latest:%d-%b-%Y}.",
             "Comparison basis: each quarter is compared with the SAME quarter a year earlier (e.g. JAS 2026 vs JAS 2025). Quarter-by-quarter trend is shown for context only.",
             "Units = quantity net of returns (return invoices '-SR-' and negative-price lines are subtracted). Revenue = sold_price x qty (returns reduce it).",
             "Merchandise only: services, warranties/care plans, schemes, gifts, stationery, spares, demo and other non-merchandise categories are excluded; branches SMC and 3GH excluded.",
             "Unit counts include lines priced under Rs 1 (free items / exchange-intake lines) - the same definition used by every Ask AI answer. Revenue is not affected by them. See the table to the left for how many there are.",
             "Quarters are calendar quarters (JFM, AMJ, JAS, OND). The store's first quarter is a part-quarter; in-progress quarters are not used in the comparisons.",
             "Products with fewer than 30 units in the base quarter are labelled 'Small base' and given no percentage. Totals in the Summary include all merchandise categories; product sheets cover the 18 focus categories."]
    for i, t in enumerate(notes):
        wn.cell(row=i + 1, column=2 + 2 * len(ql) + 1, value=t)
    wn.column_dimensions[get_column_letter(3 + 2 * len(ql))].width = 150
    wn.cell(row=1, column=3 + 2 * len(ql)).font = Font(bold=True)
    os.makedirs(A.EXPORT_DIR, exist_ok=True)
    fname = f"insights_store_qoq_{re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_')}_{uuid.uuid4().hex[:10]}.xlsx"
    wb.save(os.path.join(A.EXPORT_DIR, fname))

    # chat table: product-wise same-quarter comparison, key products first
    tbl_rows = []
    for c in order[:22]:
        i = prim[c]
        tbl_rows.append([mark(c) + c, f"{i['ub']:,}", f"{i['uc']:,}", f"{i['du']:+,}", _fp(i['uc'], i['ub']) if i['pu'] is not None else '-',
                         inr(i['rb']), inr(i['rc']), _fp(i['rc'], i['rb']) if i['pr'] is not None else '-', i['status']])
    cards = [{"label": f"{labL} Revenue", "value": inr(tr), "color": "#2563eb"},
             {"label": f"vs {labB}", "value": _fp(tr, trb), "color": "#059669"},
             {"label": "Products declining (units)", "value": str(len(declining)), "color": "#dc2626"},
             {"label": "Declining in every comparison", "value": str(len(persist)) if len(pairs) >= 2 else '-', "color": "#d97706"}]
    return {"answer": "\n".join(ans), "cards": cards,
            "table": {"headers": ["Product", f"Units {labB}", f"Units {labL}", "Change", "%", f"Revenue {labB}", f"Revenue {labL}", "Rev %", "Status"], "rows": tbl_rows},
            "download": {"url": f"/api/ai/download/{fname}", "filename": fname},
            "suggestions": [f"Overall report of {name} and give insights", f"Insights {labL} vs {labB} for {name}"]}
