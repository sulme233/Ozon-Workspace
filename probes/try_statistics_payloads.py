import json, pathlib, requests, itertools
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
tr.raise_for_status()
token = tr.json()['access_token']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'application/json'}
cl = requests.get('https://api-performance.ozon.ru/api/client/campaign', headers=headers, timeout=30)
cl.raise_for_status()
campaigns = cl.json().get('list', [])
if not campaigns:
    print('NO_CAMPAIGNS')
    raise SystemExit(0)
cid = campaigns[0]['id']
print('CAMPAIGN_ID', cid)
url = 'https://api-performance.ozon.ru/api/client/statistics'
payloads = [
    {'campaign': [cid]},
    {'campaigns': [cid]},
    {'campaignId': cid},
    {'campaign_id': cid},
    {'campaign': [int(cid)]},
    {'campaigns': [int(cid)]},
    {'campaign': [cid], 'dateFrom': '2026-03-25', 'dateTo': '2026-03-25'},
    {'campaigns': [cid], 'dateFrom': '2026-03-25', 'dateTo': '2026-03-25'},
    {'campaign': [cid], 'fromDate': '2026-03-25', 'toDate': '2026-03-25'},
    {'campaigns': [cid], 'fromDate': '2026-03-25', 'toDate': '2026-03-25'},
    {'campaign': [cid], 'date_from': '2026-03-25', 'date_to': '2026-03-25'},
    {'campaigns': [cid], 'date_from': '2026-03-25', 'date_to': '2026-03-25'},
]
for p in payloads:
    try:
        r = requests.post(url, headers=headers, json=p, timeout=30)
        print('---')
        print('PAYLOAD', json.dumps(p, ensure_ascii=False))
        print('STATUS', r.status_code)
        print('BODY', r.text[:800].replace('\n',' '))
    except Exception as e:
        print('---')
        print('PAYLOAD', json.dumps(p, ensure_ascii=False))
        print('ERROR', type(e).__name__, str(e))
