import urllib.request, json
lines = open('backend/directsync.py').read()
api_key = [l.split('=')[1].strip().strip('\"\'') for l in lines.split('\n') if 'DRIVE_API_KEY' in l][0]

url = f'https://www.googleapis.com/drive/v3/files?key={api_key}&q=trashed=false+and+name+contains+%27Bathery%27'
try:
    req = urllib.request.urlopen(url)
    data = json.loads(req.read().decode())
    for f in data.get('files', []):
        print(f['name'])
except Exception as e:
    print(e)
