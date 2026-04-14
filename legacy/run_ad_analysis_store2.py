import json, pathlib, requests, datetime, sys
sys.stdout.reconfigure(encoding='utf-8')
cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
store = next(s for s in cfg['stores'] if s['store_name'] == '二店')
perf = store['performance_api']

def get_token():
    r = requests.post(
        'https://api-performance.ozon.ru/api/client/token',
        json={'client_id': perf['client_id'], 'client_secret': perf['client_secret'], 'grant_type': 'client_credentials'},
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=30
    )
    r.raise_for_status()
    return r.json()['access_token']

def safe_json(r):
    try:
        return r.json()
    except Exception:
        return {'raw': r.text[:1000]}

token = get_token()
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
# 最近7天
end = datetime.date.today()
start = end - datetime.timedelta(days=6)
q = {'dateFrom': start.isoformat(), 'dateTo': end.isoformat()}

campaign_resp = requests.get('https://api-performance.ozon.ru/api/client/campaign', headers=headers, timeout=30)
campaign_data = safe_json(campaign_resp)
campaigns = campaign_data.get('list', []) if isinstance(campaign_data, dict) else []
# 只保留 SKU 广告
sku_campaigns = [c for c in campaigns if str(c.get('advObjectType')) == 'SKU']
ids = [str(c.get('id')) for c in sku_campaigns if c.get('id')]

result = {
    'store_name': store['store_name'],
    'store_code': store['store_code'],
    'date_from': start.isoformat(),
    'date_to': end.isoformat(),
    'campaign_count': len(sku_campaigns),
    'campaigns': sku_campaigns[:20],
    'product_stats_status': None,
    'product_stats_preview': None,
    'daily_stats_status': None,
    'daily_stats_preview': None,
    'expense_stats_status': None,
    'expense_stats_preview': None,
}

if ids:
    qp = [('campaignIds', cid) for cid in ids[:10]] + [('dateFrom', start.isoformat()), ('dateTo', end.isoformat())]
    r1 = requests.get('https://api-performance.ozon.ru/api/client/statistics/campaign/product', headers=headers, params=qp, timeout=60)
    result['product_stats_status'] = r1.status_code
    result['product_stats_preview'] = safe_json(r1)

    r2 = requests.get('https://api-performance.ozon.ru/api/client/statistics/daily', headers=headers, params=qp, timeout=60)
    result['daily_stats_status'] = r2.status_code
    result['daily_stats_preview'] = safe_json(r2)

    r3 = requests.get('https://api-performance.ozon.ru/api/client/statistics/expense', headers=headers, params=qp, timeout=60)
    result['expense_stats_status'] = r3.status_code
    result['expense_stats_preview'] = safe_json(r3)

print(json.dumps(result, ensure_ascii=False, indent=2))
