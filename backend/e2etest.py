"""Full end-to-end sync test - download, parse, match mobile numbers."""
import sqlite3, json, io, re, urllib.request, sys
from openpyxl import load_workbook

print("=== Full Sync End-to-End Test ===", flush=True)

DRIVE_URL = "https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec"

# Step 1: Get Drive files
print("\n1. Fetching Drive files...", flush=True)
req = urllib.request.Request(DRIVE_URL)
with urllib.request.urlopen(req, timeout=30) as res:
    files = json.loads(res.read().decode())
print(f"   Found {len(files)} files: {[f['name'] for f in files]}", flush=True)

# Step 2: Download first file (Vypin)
vypin_file = next((f for f in files if 'vypin' in f['name'].lower()), files[0])
print(f"\n2. Downloading '{vypin_file['name']}'...", flush=True)
url = f"https://drive.google.com/uc?export=download&id={vypin_file['id']}&confirm=t"
req2 = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req2, timeout=120) as r:
    content = r.read()
print(f"   Size: {len(content):,} bytes, Is XLSX: {content[:2] == b'PK'}", flush=True)

# Step 3: Parse with openpyxl
print("\n3. Parsing Excel file...", flush=True)
try:
    wb = load_workbook(io.BytesIO(content), data_only=True)
    sheet = wb.active
    print(f"   Sheet name: {sheet.title}, dimensions: {sheet.dimensions}", flush=True)
    print(f"   Max row: {sheet.max_row}, Max col: {sheet.max_column}", flush=True)
    
    # Find header row
    best_row = 1
    max_vals = 0
    headers = []
    for i, row in enumerate(sheet.iter_rows(min_row=1, max_row=10, values_only=True), 1):
        str_vals = [str(c).strip() for c in row if c is not None and str(c).strip() != '']
        if len(str_vals) > max_vals:
            max_vals = len(str_vals)
            best_row = i
            headers = list(row)
    print(f"   Header row: {best_row}, headers: {[str(h) for h in headers[:5]]}", flush=True)
    
    # Count valid mobile numbers
    mobile_count = 0
    sample_mobiles = []
    NOISE_KEYS = ['mobile', 'phone', 'contact', 'mobilenumber', 'phonenumber', 'mobileno', 'phoneno', 'contactno', 'customermobile']
    
    for row in sheet.iter_rows(min_row=best_row + 1, values_only=True):
        if not any(row): continue
        row_dict = dict(zip(headers, row))
        
        # Try to find mobile
        mobile = None
        for k, v in row_dict.items():
            if not k: continue
            clean_k = re.sub(r'[^a-z0-9]', '', str(k).lower())
            if clean_k in NOISE_KEYS and v:
                mobile_str = re.sub(r'\D', '', str(v))
                if len(mobile_str) >= 10:
                    mobile = mobile_str[-10:]
                    break
        
        if not mobile:
            # Fallback: first column
            first_val = str(list(row_dict.values())[0] if row_dict else '').strip()
            clean_val = re.sub(r'\D', '', first_val)
            if len(clean_val) >= 10:
                mobile = clean_val[-10:]
        
        if mobile:
            mobile_count += 1
            if len(sample_mobiles) < 3:
                sample_mobiles.append(mobile)
    
    print(f"   Valid mobile numbers found: {mobile_count:,}", flush=True)
    print(f"   Sample mobiles: {sample_mobiles}", flush=True)
    
except Exception as e:
    import traceback
    print(f"   PARSE ERROR: {e}", flush=True)
    traceback.print_exc()

print("\n=== Test complete ===", flush=True)
