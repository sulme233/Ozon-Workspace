import json, pathlib, requests
cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
store = next(s for s in cfg['stores'] if s['store_name'] == '二店')
perf = store['performance_api']
tr = requests.post(
    'https://api-performance.ozon.ru/api/client/token',
    json={
        'client_id': perf['client_id'],
        'client_secret': perf['client_secret'],
        'grant_type': 'client_credentials'
    },
    headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
    timeout=30
)
print('TOKEN_STATUS', tr.status_code)
tr.raise_for_status()
token = tr.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'application/json'}
endpoints = [
    ('GET', 'https://api-performance.ozon.ru/api/client/campaign', None),
    ('GET', 'https://api-performance.ozon.ru/api/client/campaigns', None),
    ('POST', 'https://api-performance.ozon.ru/api/client/campaign/list', {}),
    ('POST', 'https://api-performance.ozon.ru/api/client/statistics', {}),
    ('POST', 'https://api-performance.ozon.ru/api/client/report', {}),
]
for method, url, body in endpoints:
    try:
        if method == 'GET':
            r = requests.get(url, headers=headers, timeout=30)
        else:
            r = requests.post(url, headers=headers, json=body, timeout=30)
        txt = r.text[:500].replace('\n', ' ')
        print('---')
        print(method, url)
        print('STATUS', r.status_code)
        print('BODY', txt)
    except Exception as e:
        print('---')
        print(method, url)
        print('ERROR', type(e).__name__, str(e))
