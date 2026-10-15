import urllib.request
import json
url = "https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec"
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=30) as res:
    data = json.loads(res.read().decode('utf-8'))
for file_info in data:
    if 'kanjirappally' in file_info['name'].lower():
        print(file_info)
