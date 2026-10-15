import urllib.request
import json
try:
    response = urllib.request.urlopen('http://127.0.0.1:8000/api/campaign/31325/store-sales')
    data = json.loads(response.read().decode())
    print("Branch Code:", data.get('branch'))
    print("Branch Name:", data.get('branch_name'))
    print("Total Revenue:", data.get('total_revenue'))
except Exception as e:
    print(e)
