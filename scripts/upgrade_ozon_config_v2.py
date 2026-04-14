import json, pathlib
src = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(src.read_text(encoding='utf-8-sig'))
new_stores = []
for s in data.get('stores', []):
    new_stores.append({
        'store_name': s.get('store_name', ''),
        'store_code': s.get('store_code', ''),
        'enabled': s.get('enabled', True),
        'timezone': s.get('timezone', 'Asia/Shanghai'),
        'currency': s.get('currency', 'RUB'),
        'notes': s.get('notes', ''),
        'seller_api': {
            'client_id': s.get('client_id', ''),
            'api_key': s.get('api_key', '')
        },
        'performance_api': {
            'client_id': '',
            'api_key': ''
        }
    })
out = {'stores': new_stores}
src.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print('upgraded', len(new_stores))
