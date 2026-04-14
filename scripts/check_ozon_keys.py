import json, pathlib, sys, requests

cfg_path = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(cfg_path.read_text(encoding='utf-8-sig'))

# 轻量认证测试：用 seller API 一个常见只读接口试探
CANDIDATES = [
    'https://api-seller.ozon.ru/v1/description-category/tree',
    'https://api-seller.ozon.ru/v1/category/tree',
]

results = []
for store in data.get('stores', []):
    if not store.get('enabled', True):
        continue
    headers = {
        'Client-Id': str(store.get('client_id', '')).strip(),
        'Api-Key': str(store.get('api_key', '')).strip(),
        'Content-Type': 'application/json'
    }
    payload = {}
    ok = False
    msg = '未检测'
    status = None
    for url in CANDIDATES:
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            status = r.status_code
            text = r.text[:500]
            if r.status_code == 200:
                ok = True
                msg = '可用'
                break
            if r.status_code in (401, 403):
                msg = f'认证失败/无权限 ({r.status_code})'
                break
            if r.status_code == 400:
                # 400 通常说明认证过了，但请求体或接口参数不对
                ok = True
                msg = '凭据可用（接口参数不匹配）'
                break
            msg = f'接口返回 {r.status_code}: {text}'
        except Exception as e:
            msg = f'请求异常: {type(e).__name__}: {e}'
    results.append({'store_name': store.get('store_name',''), 'result': msg, 'ok': ok, 'status': status})

print(json.dumps(results, ensure_ascii=False, indent=2))
