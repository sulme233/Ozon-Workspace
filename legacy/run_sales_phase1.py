import json, pathlib, requests, datetime, sys
sys.stdout.reconfigure(encoding='utf-8')
cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
end = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
start = end - datetime.timedelta(days=7)
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
    body = {
        'filter': {
            'date': {
                'from': start.isoformat() + 'Z',
                'to': end.isoformat() + 'Z'
            },
            'transaction_type': 'all',
            'operation_type': []
        },
        'page': 1,
        'page_size': 1000
    }
    try:
        r = requests.post('https://api-seller.ozon.ru/v3/finance/transaction/list', headers=headers, json=body, timeout=60)
        if r.status_code != 200:
            results.append({'store_name': s['store_name'], 'status': r.status_code, 'summary': None})
            continue
        data = r.json().get('result', {})
        ops = data.get('operations', [])
        sales_amount = 0.0
        service_amount = 0.0
        orders_count = 0
        for op in ops:
            amount = float(op.get('amount') or 0)
            typ = str(op.get('type') or '')
            op_name = str(op.get('operation_type_name') or '')
            if typ == 'orders' or 'Продажа' in op_name or 'sale' in op_name.lower():
                sales_amount += amount
                orders_count += 1
            if typ == 'services':
                service_amount += amount
        results.append({
            'store_name': s['store_name'],
            'status': 200,
            'summary': {
                'sales_amount': round(sales_amount, 2),
                'service_amount': round(service_amount, 2),
                'orders_count': orders_count,
                'ops_count': len(ops)
            }
        })
    except Exception as e:
        results.append({'store_name': s['store_name'], 'status': 'error', 'error': str(e)[:200]})
print(json.dumps(results, ensure_ascii=False, indent=2))
