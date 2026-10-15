"""Test Google Drive download with different approaches."""
import urllib.request, http.cookiejar, sqlite3, json

# Get a real file ID from the DB (campaign_customers won't help, check drive via sheets script)
# First check what files the Drive script returns
DRIVE_URL = "https://script.google.com/macros/s/AKfycbx8RQoxU-Js-kQuY7cs90K7Rc1-pDUxq7OzLM1Oj9G5q2Kw5otr-gsJI66f_lJ1KXJCSQ/exec"

print("=== Fetching Drive file list ===")
try:
    req = urllib.request.Request(DRIVE_URL)
    with urllib.request.urlopen(req, timeout=30) as res:
        files = json.loads(res.read().decode())
    print(f"Found {len(files)} files:")
    for f in files:
        print(f"  name={f.get('name')} | id={f.get('id')}")
except Exception as e:
    print(f"ERROR: {e}")
    exit(1)

if not files:
    print("No files found!")
    exit(1)

file_id = files[0]['id']
file_name = files[0]['name']
print(f"\n=== Testing download for: {file_name} ===")

# Test 1: Original URL (no confirm)
print("\n[Test 1] Original URL (no &confirm=t)")
try:
    url1 = f"https://drive.google.com/uc?export=download&id={file_id}"
    with urllib.request.urlopen(url1, timeout=60) as r:
        data = r.read()
    print(f"  Size: {len(data):,} bytes")
    print(f"  First bytes: {data[:20]}")
    print(f"  Is HTML: {b'<html' in data[:200].lower()}")
    print(f"  Is XLSX (PK magic): {data[:2] == b'PK'}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 2: With &confirm=t
print("\n[Test 2] With &confirm=t")
try:
    url2 = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
    req2 = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req2, timeout=60) as r:
        data = r.read()
    print(f"  Size: {len(data):,} bytes")
    print(f"  Is HTML: {b'<html' in data[:200].lower()}")
    print(f"  Is XLSX (PK magic): {data[:2] == b'PK'}")
except Exception as e:
    print(f"  FAILED: {e}")

# Test 3: Cookie jar (handles redirect + confirmation)
print("\n[Test 3] Cookie jar opener")
try:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    url3 = f"https://drive.google.com/uc?export=download&id={file_id}"
    with opener.open(url3, timeout=60) as r:
        data = r.read()
    print(f"  Size: {len(data):,} bytes")
    print(f"  Is HTML: {b'<html' in data[:200].lower()}")
    print(f"  Is XLSX: {data[:2] == b'PK'}")
    if b'<html' in data[:200].lower():
        # Try to extract confirm token
        import re
        token = re.search(rb'confirm=([0-9A-Za-z_\-]+)', data)
        if token:
            print(f"  Found confirm token: {token.group(1)}")
            url3b = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={token.group(1).decode()}"
            with opener.open(url3b, timeout=120) as r2:
                data2 = r2.read()
            print(f"  Retry size: {len(data2):,} bytes | Is XLSX: {data2[:2] == b'PK'}")
except Exception as e:
    print(f"  FAILED: {e}")

print("\nDone.")
