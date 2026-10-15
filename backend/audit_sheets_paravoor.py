import urllib.request, json

url = "https://script.google.com/macros/s/AKfycbwLu3feQq0BCxUFFxpUhamKLfNa5njxmJLZ4yBRY9pmPtsgBIXEFSzeVADBt5hlG9Y_DQ/exec"
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as res:
    data = json.loads(res.read().decode())

print(f"Total rows in Sheets: {len(data)}")
for i, row in enumerate(data):
    name = str(row.get('Campaign Name', ''))
    grp = str(row.get('Campaign Group', ''))
    if 'paravoor' in name.lower() or 'paravoor' in grp.lower():
        print(f"Row {i}: Name='{name}', Group='{grp}', Mode='{row.get('Campaign Mode')}', Date='{row.get('Date')}', Cost='{row.get('Actual Cost')}', Delivered='{row.get('SMS Delivered')}'")
