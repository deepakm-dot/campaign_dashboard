"""Check exact column names returned by the Google Sheets Apps Script."""
import urllib.request, json, sys
sys.stdout.reconfigure(line_buffering=True)

SHEETS_URL = "https://script.google.com/macros/s/AKfycbwLu3feQq0BCxUFFxpUhamKLfNa5njxmJLZ4yBRY9pmPtsgBIXEFSzeVADBt5hlG9Y_DQ/exec"

print("Fetching sheet data...", flush=True)
with urllib.request.urlopen(urllib.request.Request(SHEETS_URL), timeout=30) as r:
    data = json.loads(r.read().decode())

print(f"Total rows: {len(data)}", flush=True)
print(f"\nAll column keys in row 1:\n{list(data[0].keys())}", flush=True)

# Find Vypin and Paravoor WA rows
print("\n=== Vypin and Paravoor WA Store Data rows ===")
for row in data:
    name = str(row.get('Campaign Name', ''))
    ds = str(row.get('Data ', '') or row.get('Data', ''))
    mode = str(row.get('Campaign Mode', ''))
    if ('vypin' in name.lower() or 'paravoor' in name.lower()) and 'store' in ds.lower():
        print(f"\nCampaign: {name} | Mode: {mode} | Data: {ds}")
        # Print all columns and values for this row
        for k, v in row.items():
            if v and str(v).strip() not in ('', '0', 'None'):
                print(f"  {repr(k)}: {repr(v)}")
