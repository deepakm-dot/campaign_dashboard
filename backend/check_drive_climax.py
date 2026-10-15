import urllib.request, json

url = 'https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec'
with urllib.request.urlopen(url, timeout=60) as r:
    files = json.loads(r.read().decode())
print(f'Total Drive files: {len(files)}')
for f in files:
    name = f.get('name', '')
    path = (f.get('parentPath') or '') + '/' + (f.get('folder') or '') + '/' + name
    if any(k in path.lower() for k in ['climax', 'sms', 'onam', '2025', 'sept', '30']):
        print(f"Match: {path} | ID: {f.get('id')}")
