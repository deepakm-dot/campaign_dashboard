import urllib.request
import json
import csv
import io
from backend.main import query_clickhouse

url = "https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec"
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=30) as res:
    data = json.loads(res.read().decode('utf-8'))

for file_info in data:
    if 'kanjirappally' in file_info['name'].lower():
        print("Found:", file_info['name'])
        try:
            req2 = urllib.request.Request(file_info['url'])
            with urllib.request.urlopen(req2, timeout=30) as res2:
                csv_data = res2.read().decode('utf-8')
        except Exception as e:
            print("Failed to download CSV:", e)
            continue
            
        reader = csv.DictReader(io.StringIO(csv_data))
        phones = []
        for row in reader:
            p = row.get('Phone Number', row.get('phone', list(row.values())[0] if row else ''))
            p = str(p).replace('.0', '')
            p = ''.join(filter(str.isdigit, p))
            if len(p) > 10:
                p = p[-10:]
            if len(p) == 10:
                phones.append(p)
                
        if not phones:
            print("No valid phones found!")
            continue
            
        phones = tuple(phones)
        print(f"Checking {len(phones)} phones in ClickHouse for branch KJF...")
        
        q = f"""
        SELECT count(*) as cnt, sum(toFloat64(sold_price) * toInt64(qty)) as rev
        FROM azure_sales_report 
        WHERE branch = 'KJF' AND toDate(date) >= '2026-09-03' AND toDate(date) <= '2026-09-06'
        AND mobile IN {phones}
        """
        print(query_clickhouse(q))
        
        q2 = f"""
        SELECT branch, count(*) as cnt
        FROM azure_sales_report 
        WHERE toDate(date) >= '2026-09-03' AND toDate(date) <= '2026-09-06'
        AND mobile IN {phones}
        GROUP BY branch
        ORDER BY cnt DESC
        LIMIT 5
        """
        print("Purchases anywhere:")
        print(query_clickhouse(q2))
        break
