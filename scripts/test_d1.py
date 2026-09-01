import requests
import json

account_id = 'fad19865339b3a1dc3e3de4901a451bf'
db_id = '158fadb7-cc38-4692-8c99-4400eefc8d52'
token = 'cfut_JTuvlaNx2MxlRZxgJ0HGPM5ZW8uCr2cokGc63t1wbf36def6'

url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{db_id}/query'
headers = {
    'Authorization': f'Bearer {token}',
    'Content-Type': 'application/json'
}

resp = requests.post(url, headers=headers, json={'sql': 'SELECT name FROM sqlite_master WHERE type="table";'})
print('Status:', resp.status_code)
print('Response:', json.dumps(resp.json(), indent=2))
