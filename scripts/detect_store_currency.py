import json, pathlib, requests, sys
sys.stdout.reconfigure(encoding='utf-8')
p = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(p.read_text(encoding='utf-8-sig'))
results = []
for s in data.get('stores', []):
    seller = s.get('seller_api') or {}
    headers = {
        'Client-Id': str(seller.get('client_id','')).strip(),
        'Api-Key': str(seller.get('api_key','')).strip(),
        'Content-Type': 'application/json'
    }
    currency = s.get('currency', 'RUB')
    status = None
    try:
        r = requests.post('https://api-seller.ozon.ru/v1/seller/info', headers=headers, json={}, timeout=30)
        status = r.status_code
        if r.status_code == 200:
            j = r.json()
            company = j.get('company', {}) if isinstance(j, dict) else {}
            currency = company.get('currency') or currency
        else:
            pass
    except Exception:
        pass
    s['currency'] = currency
    if 'marketplace_id' not in s:
        s['marketplace_id'] = 'MARKETPLACE_ID_RU'
    results.append({'store_name': s.get('store_name',''), 'currency': currency, 'status': status})
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
