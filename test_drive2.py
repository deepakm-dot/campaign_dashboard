import urllib.request
import json

url = "https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec"
req = urllib.request.Request(url)
with urllib.request.urlopen(req, timeout=30) as res:
    data = json.loads(res.read().decode('utf-8'))

# Mock DB campaigns
db_campaigns = [{'id': 31352, 'campaign_name': 'Kanjirappally Future'}]

for file_info in data:
    file_name = file_info['name']
    
    for camp in db_campaigns:
        c_name = camp['campaign_name'].lower().strip()
        if c_name in file_name.lower():
            print(f"MATCH: {c_name} -> {file_name}")
        else:
            if 'kanjirappally' in file_name.lower():
                print(f"NO MATCH: {c_name} -> {file_name}")
