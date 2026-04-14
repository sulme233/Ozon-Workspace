import json, pathlib, requests
cfg_path = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(cfg_path.read_text(encoding='utf-8-sig'))

# 轻量测试 Performance API：先尝试文档入口/基础路径探测
CANDIDATES = [
    'https://performance.ozon.ru',
    'https://api-performance.ozon.ru',
    'https://api-performance.ozon.ru/api/client/statistics',
    'https://api-performance.ozon.ru/api/client/campaign',
]

results = []
for store in data.get('stores', []):
    if not store.get('enabled', True):
        continue
    perf = store.get('performance_api') or {}
    client_id = str(perf.get('client_id', '')).strip()
    api_key = str(perf.get('api_key', '')).strip()
    if not client_id or not api_key:
        results.append({'store_name': store.get('store_name',''), 'result': '未填写 performance_api', 'ok': False})
        continue

    headers = {
        'Client-Id': client_id,
        'Api-Key': api_key,
        'Content-Type': 'application/json'
    }
    ok = False
    msg = '未检测'
    status = None
    for url in CANDIDATES:
        try:
            if url.endswith('/statistics') or url.endswith('/campaign'):
                r = requests.post(url, headers=headers, json={}, timeout=20)
            else:
                r = requests.get(url, headers=headers, timeout=20)
            status = r.status_code
            text = r.text[:300]
            if r.status_code == 200:
                ok = True
                msg = '可用'
                break
            if r.status_code in (400, 401, 403):
                msg = f'接口返回 {r.status_code}'
                break
            msg = f'接口返回 {r.status_code}'
        except Exception as e:
            msg = f'请求异常: {type(e).__name__}'
    results.append({'store_name': store.get('store_name',''), 'result': msg, 'ok': ok, 'status': status})

print(json.dumps(results, ensure_ascii=False, indent=2))
