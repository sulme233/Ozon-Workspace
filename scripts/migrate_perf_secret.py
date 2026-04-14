import json, pathlib
p = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(p.read_text(encoding='utf-8-sig'))
changed = 0
for s in data.get('stores', []):
    perf = s.get('performance_api')
    if isinstance(perf, dict) and 'api_key' in perf:
        perf['client_secret'] = perf.pop('api_key')
        changed += 1
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print('changed', changed)
