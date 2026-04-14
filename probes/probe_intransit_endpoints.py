import json, pathlib, requests, datetime, sys
sys.stdout.reconfigure(encoding='utf-8')
cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
# 先拿二店2 探路，它最有库存和广告问题
store = next(s for s in cfg['stores'] if s['store_name'] == '二店2')
seller = store['seller_api']
headers = {
    'Client-Id': str(seller.get('client_id','')).strip(),
    'Api-Key': str(seller.get('api_key','')).strip(),
    'Content-Type': 'application/json'
}
probes = [
    ('POST','https://api-seller.ozon.ru/v1/carriage/get', {'carriage_id': 0}),
    ('POST','https://api-seller.ozon.ru/v1/assembly/carriage/posting/list', {'cursor':'','filter': {'delivery_method_id': 0}, 'limit': 10}),
    ('POST','https://api-seller.ozon.ru/v1/assembly/carriage/product/list', {'cursor':'','filter': {'delivery_method_id': 0}, 'limit': 10}),
    ('POST','https://api-seller.ozon.ru/v1/assembly/fbs/posting/list', {'cursor':'','filter': {'delivery_method_id': 0}, 'limit': 10, 'sort_dir': 'ASC'}),
    ('POST','https://api-seller.ozon.ru/v1/assembly/fbs/product/list', {'filter': {'delivery_method_id': 0}, 'limit': 10, 'offset': 0, 'sort_dir': 'ASC'}),
    ('POST','https://api-seller.ozon.ru/v1/supply-order/bundle', {'bundle_ids': ['0'], 'limit': 10, 'sort_field': 'NAME', 'is_asc': True}),
]
results = []
for method, url, body in probes:
    try:
        r = requests.post(url, headers=headers, json=body, timeout=60)
        txt = r.text[:800].replace('\n',' ')
        results.append({'url': url, 'status': r.status_code, 'body': txt})
    except Exception as e:
        results.append({'url': url, 'status': 'error', 'body': str(e)})
print(json.dumps(results, ensure_ascii=False, indent=2))
