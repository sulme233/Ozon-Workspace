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
        'warehouse_stock_samples': [],
        'status': 200
    }
    try:
        wr = requests.post('https://api-seller.ozon.ru/v2/warehouse/list', headers=headers, json={'limit': 50, 'cursor': ''}, timeout=60)
        whs = wr.json().get('warehouses', []) if wr.status_code == 200 else []
        sample = []
        for w in whs[:3]:
            wid = w.get('warehouse_id')
            try:
                sr = requests.post('https://api-seller.ozon.ru/v1/product/info/warehouse/stocks', headers=headers, json={
                    'cursor': '', 'limit': 10, 'warehouse_id': wid
                }, timeout=60)
                if sr.status_code == 200:
                    sj = sr.json()
                    stocks = sj.get('stocks', []) if isinstance(sj, dict) else []
                    present = sum(int(x.get('present') or 0) for x in stocks)
                    reserved = sum(int(x.get('reserved') or 0) for x in stocks)
                    sample.append({
                        'warehouse_id': wid,
                        'warehouse_name': w.get('name'),
                        'present_sum_top10': present,
                        'reserved_sum_top10': reserved,
                        'sample_count': len(stocks)
                    })
            except Exception:
                pass
        store_result['warehouse_stock_samples'] = sample
    except Exception as e:
        store_result['status'] = 'error'
        store_result['error'] = str(e)[:200]
    results.append(store_result)
print(json.dumps(results, ensure_ascii=False, indent=2))
