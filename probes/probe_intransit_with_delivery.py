import json, pathlib, requests, datetime, sys
sys.stdout.reconfigure(encoding='utf-8')
cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
store = next(s for s in cfg['stores'] if s['store_name'] == '二店2')
seller = store['seller_api']
headers = {
    'Client-Id': str(seller.get('client_id','')).strip(),
    'Api-Key': str(seller.get('api_key','')).strip(),
    'Content-Type': 'application/json'
}
# 取一个真实 delivery_method_id
wr = requests.post('https://api-seller.ozon.ru/v2/warehouse/list', headers=headers, json={'limit': 1, 'cursor': ''}, timeout=60)
wid = wr.json().get('warehouses', [{}])[0].get('warehouse_id')
dr = requests.post('https://api-seller.ozon.ru/v2/delivery-method/list', headers=headers, json={'cursor':'','filter': {'warehouse_ids': [str(wid)]}, 'limit': 1, 'sort_dir': 'ASC'}, timeout=60)
delivery_methods = dr.json().get('delivery_methods', []) if dr.status_code == 200 else []
dmid = delivery_methods[0].get('id') if delivery_methods else None
now = datetime.datetime.utcnow()
cutoff_from = (now - datetime.timedelta(days=7)).isoformat() + 'Z'
cutoff_to = now.isoformat() + 'Z'
results = {'warehouse_id': wid, 'delivery_method_id': dmid, 'probes': []}
probes = [
    ('https://api-seller.ozon.ru/v1/assembly/carriage/posting/list', {'cursor':'','filter': {'delivery_method_id': dmid, 'cutoff_from': cutoff_from, 'cutoff_to': cutoff_to}, 'limit': 10}),
    ('https://api-seller.ozon.ru/v1/assembly/carriage/product/list', {'cursor':'','filter': {'delivery_method_id': dmid, 'cutoff_from': cutoff_from, 'cutoff_to': cutoff_to}, 'limit': 10}),
    ('https://api-seller.ozon.ru/v1/assembly/fbs/posting/list', {'cursor':'','filter': {'delivery_method_id': dmid, 'cutoff_from': cutoff_from, 'cutoff_to': cutoff_to}, 'limit': 10, 'sort_dir': 'ASC'}),
    ('https://api-seller.ozon.ru/v1/assembly/fbs/product/list', {'filter': {'delivery_method_id': dmid, 'cutoff_from': cutoff_from, 'cutoff_to': cutoff_to}, 'limit': 10, 'offset': 0, 'sort_dir': 'ASC'}),
]
for url, body in probes:
    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        results['probes'].append({'url': url, 'status': r.status_code, 'body': r.text[:1200].replace('\n',' ')})
    except Exception as e:
        results['probes'].append({'url': url, 'status': 'error', 'body': str(e)})
print(json.dumps(results, ensure_ascii=False, indent=2))
