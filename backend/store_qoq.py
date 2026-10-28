"""Quarter-to-quarter, product-wise analysis for a single store (from its real opening date), with declining products."""
import os
import re
import uuid
import datetime as dt
from collections import defaultdict

from store_review import (PROD, QTY, REV, _d, _f, _pct, _fp, _qstart, _qend, _quarter_label, _first_sales)

MIN_BASE = 30  # ignore percentage moves on tiny bases (units)


def _next_q(qs):
    return dt.date(qs.year + (qs.month + 3 > 12), (qs.month + 2) % 12 + 1, 1)


def store_qoq(code, name, latest_date_str):
    import ai_service as A
    q = lambda sql, t=120: A.ch_query(sql, timeout=t, quote64=True) or []
    inr = A.format_inr
    latest = _d(latest_date_str)
    first = _first_sales(A.ch_query).get(code)
    if not first:
        return {"answer": f"No sales found for {name}.", "cards": [], "table": None, "suggestions": []}
    base_filter = f"s.item_code NOT LIKE 'SRV%' AND {PROD} != '' AND {PROD} NOT IN ({A._EXCL_CATS})"

    # quarter x category (units net of returns, revenue)
    rows = q(f"""SELECT toString(toStartOfQuarter(toDate(s.date))) AS qs, {PROD} AS grp, sum({QTY}) AS u, sum({REV}) AS r,
                        sumIf({QTY}, s.sold_price >= 0 AND s.sold_price < 1 AND s.invoice_no NOT LIKE '%-SR-%') AS zu
                 FROM azure_sales_report s LEFT JOIN item_master im ON im.item_code = s.item_code
                 WHERE s.branch = '{code}' AND toDate(s.date) >= '{first}' AND {base_filter} GROUP BY qs, grp""")
    data = defaultdict(lambda: [0, 0.0])
    zero = defaultdict(int)  # (quarter, category) -> units on lines priced under Rs 1 (free items / exchange intake)
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
    brands = sorted({k[1] for k in bd}, key=lambda b: -bd.get((comp[-1], b), [0, 0])[0])

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

    L = comp[-1]; P = comp[-2]; Y = comp[-5] if len(comp) >= 5 else None
    labL, labP, labY = _quarter_label(L), _quarter_label(P), (_quarter_label(Y) if Y else None)

    # ---- per-category status ----
    focus = [c for c in cats if c in A.FOCUS_CATS or c in A.KEY_CATS]
    info = {}
    for c in focus:
        us = [U(c, k) for k in comp]
        qoq = _pct(us[-1], us[-2]) if us[-2] >= MIN_BASE else None
        yoy = _pct(us[-1], U(c, Y)) if (Y and U(c, Y) >= MIN_BASE) else None
        streak = 0
        for i in range(len(us) - 1, 0, -1):
            if us[i] < us[i - 1]:
                streak += 1
            else:
                break
        dq = qoq is not None and qoq < 0
        dy = yoy is not None and yoy < 0
        status = ('Declining (QoQ & YoY)' if dq and dy else 'Down YoY' if dy else 'Down QoQ (check seasonality)' if dq else 'Growing' if (qoq is not None or yoy is not None) else 'Small base')
        info[c] = {'us': us, 'qoq': qoq, 'yoy': yoy, 'streak': streak, 'status': status,
                   'dU_q': us[-1] - us[-2], 'dU_y': (us[-1] - U(c, Y)) if Y else None,
                   'dR_q': R(c, L) - R(c, P), 'dR_y': (R(c, L) - R(c, Y)) if Y else None}
    order = sorted(focus, key=lambda c: (0 if c in A.KEY_CATS else 1, -info[c]['us'][-1]))

    both = sorted([c for c in focus if info[c]['status'].startswith('Declining')], key=lambda c: info[c]['dU_q'])
    yoy_only = sorted([c for c in focus if info[c]['status'] == 'Down YoY'], key=lambda c: info[c]['dU_y'])
    qoq_only = sorted([c for c in focus if info[c]['status'].startswith('Down QoQ')], key=lambda c: info[c]['dU_q'])
    streaks = sorted([c for c in focus if info[c]['streak'] >= 2 and info[c]['us'][-2] >= MIN_BASE], key=lambda c: -info[c]['streak'])
    mark = lambda c: '★ ' if c in A.KEY_CATS else ''

    def line(c, kind):
        i = info[c]
        if kind == 'q':
            return f"{mark(c)}{c} {i['us'][-2]:,} -> {i['us'][-1]:,} units ({i['dU_q']:+,}, {_fp(i['us'][-1], i['us'][-2])}); revenue {_fp(R(c, L), R(c, P))} ({inr(abs(i['dR_q']))} {'lower' if i['dR_q'] < 0 else 'higher'})"
        return f"{mark(c)}{c} {U(c, Y):,} -> {i['us'][-1]:,} units ({i['dU_y']:+,}, {_fp(i['us'][-1], U(c, Y))}); revenue {_fp(R(c, L), R(c, Y))}"

    # ---- chat answer ----
    ans = [f"**Quarter-to-quarter analysis: {name}** - from inauguration {first:%d-%b-%Y} to {latest:%d-%b-%Y}. Merchandise only (services, warranties, gifts, stationery, spares, demo excluded); units net of returns. "
           f"Complete quarters: {', '.join(_quarter_label(k) for k in comp)}" + (f"; {_quarter_label(part[-1])} is in progress." if part else ".")]
    ans.append("\n**Store totals by quarter**")
    for i, k in enumerate(comp):
        qq = f"QoQ {_fp(tot_r[k], tot_r[comp[i - 1]])}" if i else "first quarter (opened 5-Apr, so ~87 days)"
        yy = f", YoY {_fp(tot_r[k], tot_r[comp[i - 4]])}" if i >= 4 else ""
        ans.append(f"- {_quarter_label(k)}: {inr(tot_r[k])} on {tot_u[k]:,} units - {qq}{yy}")
    if part:
        k = part[-1]
        ans.append(f"- {_quarter_label(k)} (to {latest:%d-%b}): {inr(tot_r[k])} on {tot_u[k]:,} units")

    ans.append(f"\n**Declining products - {labL} vs {labP} (QoQ){' and vs ' + labY + ' (YoY)' if Y else ''}** (★ = key product; categories with under {MIN_BASE} units in the base quarter ignored)")
    if both:
        ans.append(f"Down both QoQ and YoY (the real concern):")
        ans.extend(f"- {line(c, 'q')}; YoY {_fp(info[c]['us'][-1], U(c, Y))} ({info[c]['dU_y']:+,} units)" for c in both[:10])
    else:
        ans.append("No focus product is down on both QoQ and YoY.")
    if yoy_only:
        ans.append(f"Down year on year only ({labL} vs {labY}):")
        ans.extend(f"- {line(c, 'y')}" for c in yoy_only[:8])
    if qoq_only:
        ans.append(f"Down quarter on quarter only (may be seasonal - Onam/festive and summer swings):")
        ans.extend(f"- {line(c, 'q')}" for c in qoq_only[:8])
    if streaks:
        ans.append("Consecutive quarterly declines: " + "; ".join(f"{mark(c)}{c} ({info[c]['streak']} quarters in a row, {info[c]['us'][-1 - info[c]['streak']]:,} -> {info[c]['us'][-1]:,})" for c in streaks[:8]) + ".")
    if ytd:
        cu = ytd['rows']
        dn = sorted([(c, a, b) for c, (a, b) in cu.items() if c in focus and b >= MIN_BASE and a < b], key=lambda x: x[1] - x[2])[:6]
        if dn:
            ans.append(f"{_quarter_label(part[-1])} so far ({ytd['cur'][0]:%d-%b} to {ytd['cur'][1]:%d-%b}) vs same dates last year: " +
                       "; ".join(f"{mark(c)}{c} {b:,} -> {a:,} ({_fp(a, b)})" for c, a, b in dn) + ". Caution: Diwali run-up fell inside these dates in 2025 (20-Oct) but falls on 8-Nov in 2026, so October is not like-for-like.")
    if brands:
        bl = []
        for b in brands[:7]:
            bu = [bd.get((k, b), [0, 0])[0] for k in comp]
            if bu[-2] >= MIN_BASE // 2 and bu[-1] < bu[-2]:
                bl.append((b, bu[-2], bu[-1]))
        if bl:
            ans.append(f"Mobile brands down vs {labP}: " + "; ".join(f"{b} {a:,} -> {z:,} ({_fp(z, a)})" for b, a, z in sorted(bl, key=lambda x: x[2] - x[1])[:5]) + ".")

    zk = [(c, zero.get((L, c), 0), U(c, L)) for c in A.KEY_CATS if zero.get((L, c), 0)]
    if zk:
        ans.append(f"\n**Data note ({labL} units):** unit counts include lines priced under Rs 1 (free items / exchange intake), as in every other Ask AI answer - " +
                   "; ".join(f"{c} {z:,} of {t:,}" for c, z, t in zk) + ". Revenue is unaffected. The Excel 'Data Notes' sheet shows this for every product and quarter.")
    ans.append("\n**How to read it:** QoQ moves are partly seasonal (AC peaks in AMJ, Onam lifts JAS, Diwali lifts OND), so YoY is the cleaner test - but the first-year base was a ramp-up. The full quarter-by-product matrix (units, revenue, QoQ/YoY per product, brands) is in the Excel.")

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
    wsum = sheet('Summary', ['Quarter', 'Units', 'Revenue', 'Revenue QoQ %', 'Revenue YoY %', 'Units QoQ %', 'Complete?'],
                 [[_quarter_label(k), tot_u[k], tot_r[k], _pct(tot_r[k], tot_r[all_q[i - 1]]) if i else None, _pct(tot_r[k], tot_r[all_q[i - 4]]) if i >= 4 else None,
                   _pct(tot_u[k], tot_u[all_q[i - 1]]) if i else None, 'Yes' if k in comp else 'In progress'] for i, k in enumerate(all_q)], num=(2, 3), pct=(4, 5, 6))
    sheet('Units by Quarter', ['Product'] + ql + [f'QoQ % ({labP}->{labL})', f'YoY % ({labY}->{labL})' if Y else 'YoY %', 'Consecutive declines', 'Status'],
          [[c] + info[c]['us'] + [info[c]['qoq'], info[c]['yoy'], info[c]['streak'], info[c]['status']] for c in order],
          num=tuple(range(2, 2 + len(ql))), pct=(2 + len(ql), 3 + len(ql)), delta=(2 + len(ql), 3 + len(ql)), keycol=1, statuscol=5 + len(ql))
    sheet('Revenue by Quarter', ['Product'] + ql + ['Revenue QoQ change', 'Revenue YoY change'],
          [[c] + [R(c, k) for k in comp] + [info[c]['dR_q'], info[c]['dR_y']] for c in order], num=tuple(range(2, 4 + len(ql))), delta=(2 + len(ql), 3 + len(ql)), keycol=1)
    sheet('Declining Products', ['Product', f'Units {labP}', f'Units {labL}', 'QoQ unit change', 'QoQ %', f'Units {labY}' if Y else 'Units YoY base', 'YoY unit change', 'YoY %', 'Revenue QoQ change', 'Revenue YoY change', 'Consecutive declines', 'Status'],
          [[c, info[c]['us'][-2], info[c]['us'][-1], info[c]['dU_q'], info[c]['qoq'], U(c, Y) if Y else None, info[c]['dU_y'], info[c]['yoy'], info[c]['dR_q'], info[c]['dR_y'], info[c]['streak'], info[c]['status']]
           for c in sorted([x for x in focus if not info[x]['status'] in ('Growing', 'Small base')], key=lambda x: (0 if info[x]['status'].startswith('Declining') else 1, info[x]['dU_q']))],
          num=(2, 3, 4, 6, 7, 9, 10), pct=(5, 8), delta=(4, 7, 9, 10), keycol=1, statuscol=12)
    sheet('All Categories', ['Product'] + [f'Units {x}' for x in ql] + [f'Revenue {x}' for x in ql],
          [[c] + [U(c, k) for k in comp] + [R(c, k) for k in comp] for c in sorted(cats, key=lambda c: -U(c, L))], num=tuple(range(2, 2 + 2 * len(ql))), keycol=1)
    if brands:
        sheet('Mobile Brands by Quarter', ['Brand'] + [f'Units {x}' for x in ql] + ['QoQ unit change'],
              [[b] + [bd.get((k, b), [0, 0])[0] for k in comp] + [bd.get((L, b), [0, 0])[0] - bd.get((P, b), [0, 0])[0]] for b in brands], num=tuple(range(2, 3 + len(ql))), delta=(2 + len(ql),))
    if ytd:
        sheet(f'{_quarter_label(part[-1])} to date', ['Product', f"Units {ytd['cur'][0]:%d-%b-%y} to {ytd['cur'][1]:%d-%b-%y}", f"Units {ytd['prev'][0]:%d-%b-%y} to {ytd['prev'][1]:%d-%b-%y}", 'Change', '%'],
              [[c, a, b, a - b, _pct(a, b)] for c, (a, b) in sorted(ytd['rows'].items(), key=lambda x: x[1][0] - x[1][1]) if c in focus], num=(2, 3, 4), pct=(5,), delta=(4,), keycol=1)

    wn = sheet('Data Notes', ['Product'] + [f'Rs0-price units {x}' for x in ql] + [f'Total units {x}' for x in ql],
               [[c] + [zero.get((k, c), 0) for k in comp] + [U(c, k) for k in comp] for c in sorted(cats, key=lambda c: -sum(zero.get((k, c), 0) for k in comp)) if any(zero.get((k, c), 0) for k in comp)],
               num=tuple(range(2, 2 + 2 * len(ql))), keycol=1)
    notes = ["DEFINITIONS USED IN THIS REPORT",
             f"Store: {name}; period: {first:%d-%b-%Y} (first trading day, first day with sales of Rs 1 lakh or more) to {latest:%d-%b-%Y}.",
             "Units = quantity net of returns (return invoices '-SR-' and negative-price lines are subtracted). Revenue = sold_price x qty (returns reduce it).",
             "Merchandise only: services, warranties/care plans, schemes, gifts, stationery, spares, demo and other non-merchandise categories are excluded; branches SMC and 3GH excluded.",
             "Unit counts include lines priced under Rs 1 (free items / exchange-intake lines) - the same definition used by every Ask AI answer. Revenue is not affected by them. See the table to the right for how many there are.",
             "Quarters are calendar quarters (JFM, AMJ, JAS, OND). The first quarter is part-quarter (store opened mid-quarter); in-progress quarters are not used for QoQ/YoY.",
             "YoY compares with the same quarter a year earlier; products with fewer than 30 units in the base quarter are not given a percentage."]
    for i, t in enumerate(notes):
        wn.cell(row=i + 1, column=2 + 2 * len(ql) + 1, value=t)
    wn.column_dimensions[get_column_letter(3 + 2 * len(ql))].width = 150
    wn.cell(row=1, column=3 + 2 * len(ql)).font = Font(bold=True)
    os.makedirs(A.EXPORT_DIR, exist_ok=True)
    fname = f"insights_store_qoq_{re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_')}_{uuid.uuid4().hex[:10]}.xlsx"
    wb.save(os.path.join(A.EXPORT_DIR, fname))

    # chat table: units by quarter for focus products, key first
    tbl_rows = []
    for c in order[:22]:
        i = info[c]
        tbl_rows.append([('★ ' if c in A.KEY_CATS else '') + c] + [f"{x:,}" for x in i['us']] + [_fp(i['us'][-1], i['us'][-2]) if i['qoq'] is not None else '-', _fp(i['us'][-1], U(c, Y)) if i['yoy'] is not None else '-', i['status']])
    cards = [{"label": f"{labL} Revenue", "value": inr(tot_r[L]), "color": "#2563eb"},
             {"label": f"QoQ vs {labP}", "value": _fp(tot_r[L], tot_r[P]), "color": "#059669"},
             {"label": "Products declining", "value": str(len(both) + len(yoy_only) + len(qoq_only)), "color": "#dc2626"},
             {"label": "Down QoQ & YoY", "value": str(len(both)), "color": "#d97706"}]
    return {"answer": "\n".join(ans), "cards": cards,
            "table": {"headers": ["Product (units)"] + ql + ["QoQ", "YoY", "Status"], "rows": tbl_rows},
            "download": {"url": f"/api/ai/download/{fname}", "filename": fname},
            "suggestions": [f"Overall report of {name} and give insights", f"Insights JAS 2026 vs JAS 2025 for {name}"]}
