import json, pathlib
p = pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json')
data = json.loads(p.read_text(encoding='utf-8-sig'))
for s in data.get('stores', []):
    s['enabled'] = True
p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print('updated', len(data.get('stores', [])))
