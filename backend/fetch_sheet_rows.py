import urllib.request
import json

url = "https://script.google.com/macros/s/AKfycbwLu3feQq0BCxUFFxpUhamKLfNa5njxmJLZ4yBRY9pmPtsgBIXEFSzeVADBt5hlG9Y_DQ/exec"
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode())

for r in data:
    sl = r.get('Sl')
    name = r.get('Campaign Name')
    group = r.get('Campaign Group')
    mode = r.get('Campaign Mode')
    data_s = r.get('Data ') or r.get('Data')
    if 'kerala' in str(name).lower() or sl in [36, 37, 66, 67] or 'climax' in str(group).lower():
        print(f"Sl: {sl} | Name: {name} | Group: {group} | Mode: {mode} | Data: {data_s} | Delivered: {r.get('SMS Delivered')}")
