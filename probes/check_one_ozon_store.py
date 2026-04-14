import json, pathlib, requests
cfg_path = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(cfg_path.read_text(encoding='utf-8-sig'))
target = '1店shiyao111111116@163.com'
CANDIDATES = [
    'https://api-seller.ozon.ru/v1/description-category/tree',
    'https://api-seller.ozon.ru/v1/category/tree',
]
for store in data.get('stores', []):
    if store.get('store_name') != target:
        continue
    headers = {
        'Client-Id': str(store.get('client_id', '')).strip(),
        'Api-Key': str(store.get('api_key', '')).strip(),
        'Content-Type': 'application/json'
    }
    payload = {}
    for url in CANDIDATES:
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            text = r.text[:300]
            if r.status_code == 200:
                print('OK 200')
                raise SystemExit(0)
            if r.status_code in (401,403):
                print(f'AUTH_FAIL {r.status_code}')
                raise SystemExit(0)
            if r.status_code == 400:
                print('OK_AUTH_BUT_BAD_PARAMS 400')
                raise SystemExit(0)
            print(f'STATUS {r.status_code} {text}')
        except Exception as e:
            print(f'ERROR {type(e).__name__}: {e}')
    raise SystemExit(0)
print('NOT_FOUND')
