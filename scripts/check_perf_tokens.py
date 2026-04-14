import json, pathlib, requests
cfg_path = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(cfg_path.read_text(encoding='utf-8-sig'))
url = 'https://api-performance.ozon.ru/api/client/token'
results = []
for store in data.get('stores', []):
    if not store.get('enabled', True):
        continue
    perf = store.get('performance_api') or {}
    client_id = str(perf.get('client_id', '')).strip()
    client_secret = str(perf.get('client_secret', '')).strip()
    if not client_id or not client_secret:
        results.append({'store_name': store.get('store_name',''), 'result': '未填写 performance_api', 'ok': False})
        continue
    payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    try:
        r = requests.post(url, json=payload, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=25)
        txt = r.text[:300]
        if r.status_code == 200:
            j = r.json()
            ok = bool(j.get('access_token'))
            exp = j.get('expires_in')
            results.append({'store_name': store.get('store_name',''), 'result': f'获取成功 expires_in={exp}', 'ok': ok, 'status': 200})
        else:
            results.append({'store_name': store.get('store_name',''), 'result': f'接口返回 {r.status_code}: {txt}', 'ok': False, 'status': r.status_code})
    except Exception as e:
        results.append({'store_name': store.get('store_name',''), 'result': f'请求异常: {type(e).__name__}: {e}', 'ok': False})
print(json.dumps(results, ensure_ascii=False, indent=2))
