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
now = datetime.datetime.utcnow()
from_dt = (now - datetime.timedelta(days=30)).isoformat() + 'Z'
to_dt = now.isoformat() + 'Z'
# 取一个真实 delivery_method_id
wr = requests.post('https://api-seller.ozon.ru/v2/warehouse/list', headers=headers, json={'limit': 1, 'cursor': ''}, timeout=60)
wid = wr.json().get('warehouses', [{}])[0].get('warehouse_id')
dr = requests.post('https://api-seller.ozon.ru/v2/delivery-method/list', headers=headers, json={'cursor':'','filter': {'warehouse_ids': [str(wid)]}, 'limit': 3, 'sort_dir': 'ASC'}, timeout=60)
delivery_methods = dr.json().get('delivery_methods', []) if dr.status_code == 200 else []
probes = []
# 1) carriage available old method
for dm in delivery_methods[:2]:
    dmid = dm.get('id')
    try:
        r = requests.post('https://api-seller.ozon.ru/v1/posting/carriage-available/list', headers=headers, json={
            'delivery_method_id': dmid,
            'departure_date': now.isoformat() + 'Z'
        }, timeout=60)
        probes.append({'step': 'carriage_available', 'delivery_method_id': dmid, 'status': r.status_code, 'body': r.text[:1200].replace('\n',' ')})
    except Exception as e:
        probes.append({'step': 'carriage_available', 'delivery_method_id': dmid, 'status': 'error', 'body': str(e)})
# 2) fbs posting list with broader date range
for dm in delivery_methods[:2]:
    dmid = dm.get('id')
    try:
        r = requests.post('https://api-seller.ozon.ru/v3/posting/fbs/list', headers=headers, json={
            'dir': 'ASC',
            'filter': {
                'since': from_dt,
                'to': to_dt,
                'delivery_method_id': [str(dmid)]
            },
            'limit': 20,
            'offset': 0,
            'with': {
                'analytics_data': True,
                'financial_data': True,
                'translit': True
            }
        }, timeout=60)
        probes.append({'step': 'fbs_posting_list', 'delivery_method_id': dmid, 'status': r.status_code, 'body': r.text[:1500].replace('\n',' ')})
    except Exception as e:
        probes.append({'step': 'fbs_posting_list', 'delivery_method_id': dmid, 'status': 'error', 'body': str(e)})
print(json.dumps({'warehouse_id': wid, 'delivery_methods': delivery_methods[:2], 'probes': probes}, ensure_ascii=False, indent=2))
