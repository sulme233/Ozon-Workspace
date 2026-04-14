import json, pathlib, requests, datetime, sys
sys.stdout.reconfigure(encoding='utf-8')
cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
store = next(s for s in cfg['stores'] if s['store_name'] == '二店')
perf = store['performance_api']

def get_token():
    r = requests.post('https://api-performance.ozon.ru/api/client/token', json={
        'client_id': perf['client_id'],
        'client_secret': perf['client_secret'],
        'grant_type': 'client_credentials'
    }, headers={'Content-Type':'application/json','Accept':'application/json'}, timeout=30)
    r.raise_for_status()
    return r.json()['access_token']

def parse_csv(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if not lines:
        return []
    header = [h.strip() for h in lines[0].split(';')]
    rows = []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(';')]
        if len(parts) < len(header):
            parts += [''] * (len(header) - len(parts))
        rows.append(dict(zip(header, parts)))
    return rows

def ru_num(s):
    s = str(s).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    if not s:
        return 0.0
    try:
        return float(s)
    except:
        return 0.0

token = get_token()
headers = {'Authorization': f'Bearer {token}', 'Accept':'application/json'}
end = datetime.date.today()
start = end - datetime.timedelta(days=6)
campaigns = requests.get('https://api-performance.ozon.ru/api/client/campaign', headers=headers, timeout=30).json().get('list', [])
sku_campaigns = [c for c in campaigns if str(c.get('advObjectType')) == 'SKU']
ids = [str(c.get('id')) for c in sku_campaigns if c.get('id')]
qp = [('campaignIds', cid) for cid in ids[:10]] + [('dateFrom', start.isoformat()), ('dateTo', end.isoformat())]
prod_resp = requests.get('https://api-performance.ozon.ru/api/client/statistics/campaign/product', headers=headers, params=qp, timeout=60)
rows = parse_csv(prod_resp.text)
# 拉对象列表（前10个活动）
objects_map = {}
for cid in ids[:10]:
    try:
        r = requests.get(f'https://api-performance.ozon.ru/api/client/campaign/{cid}/objects', headers=headers, timeout=30)
        if r.status_code == 200:
            objects_map[cid] = r.json().get('list', [])
        else:
            objects_map[cid] = []
    except:
        objects_map[cid] = []

# 输出精简结果供后续人工/自动回写
result = []
for r in rows:
    cid = str(r.get('ID','')).strip()
    result.append({
        'campaign_id': cid,
        'campaign_name': r.get('Название',''),
        'status': r.get('Статус',''),
        'promotion_type': r.get('Тип продвижения',''),
        'placement': r.get('Места размещения',''),
        'weekly_budget_rub': ru_num(r.get('Недельный бюджет, ₽','0')),
        'expense_rub': ru_num(r.get('Расход, ₽','0')),
        'impressions': int(ru_num(r.get('Показы','0'))),
        'clicks': int(ru_num(r.get('Клики','0'))),
        'cart_adds': int(ru_num(r.get('В корзину','0'))),
        'ctr_pct': ru_num(r.get('CTR','0')),
        'avg_cpc_rub': ru_num(r.get('Средняя стоимость клика, ₽','0')),
        'orders': int(ru_num(r.get('Заказы, шт.','0'))),
        'revenue_rub': ru_num(r.get('Продажи, ₽','0')),
        'drr_pct': ru_num(r.get('ДРР','0')),
        'strategy': r.get('Стратегия',''),
        'objects_count': len(objects_map.get(cid, [])),
        'object_ids_preview': ','.join([str(x.get('id','')) for x in objects_map.get(cid, [])[:5]])
    })
print(json.dumps(result, ensure_ascii=False, indent=2))
