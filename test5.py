import pickle
from googleapiclient.discovery import build

with open('token.pickle', 'rb') as token:
    creds = pickle.load(token)

service = build('drive', 'v3', credentials=creds)

results = service.files().list(
    q="trashed=false and name contains 'Bathery'",
    fields="nextPageToken, files(id, name, parents)"
).execute()

for f in results.get('files', []):
    print("File:", f['name'])
    # get parent folder names
    if f.get('parents'):
        for p in f['parents']:
            try:
                parent = service.files().get(fileId=p, fields="name").execute()
                print("  Parent:", parent['name'])
            except: pass
