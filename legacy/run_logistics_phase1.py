import json, pathlib, requests, sys
sys.stdout.reconfigure(encoding='utf-8')
cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
results = []
for s in cfg.get('stores', []):
    if not s.get('enabled', True):
        continue
    seller = s.get('seller_api') or {}
    headers = {
        'Client-Id': str(seller.get('client_id','')).strip(),
        'Api-Key': str(seller.get('api_key','')).strip(),
        'Content-Type': 'application/json'
    }
    store_result = {
        'store_name': s.get('store_name',''),
        'currency': s.get('currency',''),
        'warehouses': [],
        'warehouse_count': 0,
        'delivery_methods_count': 0,
        'status': 200
    }
    try:
        wr = requests.post('https://api-seller.ozon.ru/v2/warehouse/list', headers=headers, json={'limit': 200, 'cursor': ''}, timeout=60)
        if wr.status_code == 200:
            wj = wr.json()
            whs = wj.get('warehouses', []) if isinstance(wj, dict) else []
            store_result['warehouse_count'] = len(whs)
            for w in whs[:10]:
                wid = w.get('warehouse_id')
                name = w.get('name')
                status = w.get('status')
                try:
                    dr = requests.post('https://api-seller.ozon.ru/v2/delivery-method/list', headers=headers, json={
                        'cursor': '',
                        'filter': {'warehouse_ids': [str(wid)]},
                        'limit': 100,
                        'sort_dir': 'ASC'
                    }, timeout=60)
                    methods = []
                    if dr.status_code == 200:
                        dj = dr.json()
                        methods = dj.get('delivery_methods', []) if isinstance(dj, dict) else []
                        store_result['delivery_methods_count'] += len(methods)
                    store_result['warehouses'].append({
                        'warehouse_id': wid,
                        'name': name,
                        'status': status,
                        'delivery_methods_count': len(methods)
                    })
                except Exception:
                    store_result['warehouses'].append({
                        'warehouse_id': wid,
                        'name': name,
                        'status': status,
                        'delivery_methods_count': None
                    })
        else:
            store_result['status'] = wr.status_code
    except Exception as e:
        store_result['status'] = 'error'
        store_result['error'] = str(e)[:200]
    results.append(store_result)
print(json.dumps(results, ensure_ascii=False, indent=2))
