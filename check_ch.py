import urllib.request
import json
import base64

query = "SELECT code, branch_name FROM branch_master WHERE code='KTF'"
req = urllib.request.Request('https://pdhsuv47ec.ap-south-1.aws.clickhouse.cloud:8443/')
req.add_header('Authorization', 'Basic ' + base64.b64encode(b'default:ZFlujj9SA_Iei').decode())
req.add_header('Content-Type', 'text/plain')
req.data = (query + " FORMAT JSON").encode()

try:
    response = urllib.request.urlopen(req)
    data = json.loads(response.read().decode())['data']
    print(data)
except Exception as e:
    print(e)
