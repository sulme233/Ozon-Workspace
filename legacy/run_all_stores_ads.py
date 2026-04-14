import json, pathlib, requests, datetime, sys
sys.stdout.reconfigure(encoding='utf-8')

cfg = json.loads(pathlib.Path(r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\secrets\ozon_accounts.json').read_text(encoding='utf-8-sig'))
DOCID = 'dcgEnz0S43MoNux90_2Fr-VjNy4YNvrv5chYfEsyNJ9YUv_LdZw12fvFLgudlPbHmPZ9pxhuKVStVhQudeuvXcSA'
SHEET_DETAIL = 'kBsyKf'
SHEET_SUMMARY = 'sZIjCk'
SHEET_ALERT = 'ruC6Tw'

end = datetime.date.today()
start = end - datetime.timedelta(days=6)


def get_token(perf):
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

def classify(row):
    clicks = row['clicks']
    carts = row['cart_adds']
    orders = row['orders']
    expense = row['expense_rub']
    roas = row['roas']
    if orders >= 3 and roas >= 8:
        return '强力放量', '高表现', '高', '活动有订单且投产高，建议优先放量。'
    if clicks >= 30 and carts > 0 and orders == 0:
        return '重点优化转化', '有加购无转化', '中', '已有点击和加购，但暂无订单，优先检查价格、主图、评价和详情页。'
    if clicks >= 30 and orders == 0 and expense > 0:
        return '观察优化', '有点击无转化', '中', '已有点击和花费，但暂无订单，建议持续观察并优化转化。'
    if expense > 0 and orders == 0:
        return '观察优化', '低转化', '低', '已有花费但暂无订单，样本较小，继续观察。'
    return '继续投放', '正常', '低', '当前数据量有限，先持续跟踪。'

all_detail_records = []
all_summary_records = []
all_alert_records = []
run_report = []

for store in cfg.get('stores', []):
    if not store.get('enabled', True):
        continue
    try:
        token = get_token(store['performance_api'])
        headers = {'Authorization': f'Bearer {token}', 'Accept':'application/json'}
        campaigns = requests.get('https://api-performance.ozon.ru/api/client/campaign', headers=headers, timeout=30).json().get('list', [])
        sku_campaigns = [c for c in campaigns if str(c.get('advObjectType')) == 'SKU']
        ids = [str(c.get('id')) for c in sku_campaigns if c.get('id')][:10]
        if not ids:
            run_report.append({'store': store['store_name'], 'status': 'no_campaigns'})
            continue
        qp = [('campaignIds', cid) for cid in ids] + [('dateFrom', start.isoformat()), ('dateTo', end.isoformat())]
        product_rows = parse_csv(requests.get('https://api-performance.ozon.ru/api/client/statistics/campaign/product', headers=headers, params=qp, timeout=60).text)
        daily_rows = parse_csv(requests.get('https://api-performance.ozon.ru/api/client/statistics/daily', headers=headers, params=qp, timeout=60).text)
        objects_map = {}
        for cid in ids:
            try:
                rr = requests.get(f'https://api-performance.ozon.ru/api/client/campaign/{cid}/objects', headers=headers, timeout=30)
                objects_map[cid] = rr.json().get('list', []) if rr.status_code == 200 else []
            except:
                objects_map[cid] = []

        total_expense = total_revenue = total_orders = total_impr = total_clicks = total_carts = 0.0
        high_count = low_count = zero_count = 0
        any_reason = []
        for r in product_rows:
            cid = str(r.get('ID','')).strip()
            obj_ids = [str(x.get('id','')) for x in objects_map.get(cid, [])[:5]]
            sku = obj_ids[0] if obj_ids else cid
            expense = ru_num(r.get('Расход, ₽','0'))
            revenue = ru_num(r.get('Продажи, ₽','0'))
            orders = int(ru_num(r.get('Заказы, шт.','0')))
            impr = int(ru_num(r.get('Показы','0')))
            clicks = int(ru_num(r.get('Клики','0')))
            carts = int(ru_num(r.get('В корзину','0')))
            ctr = ru_num(r.get('CTR','0'))
            cpc = ru_num(r.get('Средняя стоимость клика, ₽','0'))
            roas = (revenue / expense) if expense else 0.0
            action, abnormal_type, risk, reason = classify({'clicks':clicks,'cart_adds':carts,'orders':orders,'expense_rub':expense,'roas':roas})
            total_expense += expense; total_revenue += revenue; total_orders += orders; total_impr += impr; total_clicks += clicks; total_carts += carts
            if action == '强力放量': high_count += 1
            if orders == 0 and expense > 0: zero_count += 1
            if action in ('重点优化转化','观察优化'): low_count += 1
            if reason not in any_reason:
                any_reason.append(reason)
            all_detail_records.append({
                'values': {
                    '日期': [{'type':'text','text': f'{start.isoformat()}~{end.isoformat()}'}],
                    '店铺名称': [{'type':'text','text': store['store_name']}],
                    '店铺代号': [{'type':'text','text': store['store_code']}],
                    'SKU': int(sku) if str(sku).isdigit() else 0,
                    '商品名称': [{'type':'text','text': r.get('Название','')}],
                    '广告活动ID': [{'type':'text','text': cid}],
                    '广告活动名称': [{'type':'text','text': r.get('Название','')}],
                    '投放工具': [{'type':'text','text': 'CPC'}],
                    '投放位置': [{'type':'text','text': r.get('Места размещения','') or r.get('Тип продвижения','')}],
                    '广告花费': round(expense,2),
                    '销售额': round(revenue,2),
                    '订单数': orders,
                    '展现量': impr,
                    '点击量': clicks,
                    'CTR': round(ctr*100 if ctr <= 1 else ctr, 2),
                    'CPC': round(cpc,2),
                    '加购数': carts,
                    '加购转化率': round((carts/clicks*100) if clicks else 0, 2),
                    'ACOS': round((expense/revenue*100) if revenue else 0, 2),
                    'ROAS': round(roas, 2),
                    '建议动作': [{'text': action}],
                    '分析结论': [{'type':'text','text': reason}],
                    '抓取时间': f'{end.isoformat()} 02:00:00'
                }
            })
            if abnormal_type != '正常':
                all_alert_records.append({
                    'values': {
                        '日期': [{'type':'text','text': f'{start.isoformat()}~{end.isoformat()}'}],
                        '店铺名称': [{'type':'text','text': store['store_name']}],
                        '店铺代号': [{'type':'text','text': store['store_code']}],
                        'SKU': int(sku) if str(sku).isdigit() else 0,
                        '商品名称': [{'type':'text','text': r.get('Название','')}],
                        '异常类型': [{'text': abnormal_type}],
                        '广告花费': round(expense,2),
                        '销售额': round(revenue,2),
                        '订单数': orders,
                        '点击量': clicks,
                        'CTR': round(ctr*100 if ctr <= 1 else ctr, 2),
                        'CPC': round(cpc,2),
                        'ROAS': round(roas,2),
                        '风险等级': [{'text': risk}],
                        '建议动作': [{'text': action}],
                        '原因说明': [{'type':'text','text': reason}],
                        '负责人': [{'type':'text','text': '待分配'}],
                        '处理状态': [{'text':'待处理'}],
                        '备注': [{'type':'text','text':'系统自动生成'}],
                        '抓取时间': f'{end.isoformat()} 02:00:00'
                    }
                })
        avg_ctr = (total_clicks/total_impr*100) if total_impr else 0
        avg_cpc = (total_expense/total_clicks) if total_clicks else 0
        avg_cart = (total_carts/total_clicks*100) if total_clicks else 0
        roas_total = (total_revenue/total_expense) if total_expense else 0
        risk = '高' if zero_count > 3 else ('中' if zero_count > 0 else '低')
        summary_text = '；'.join(any_reason[:3]) if any_reason else '广告数据已成功拉取，继续观察。'
        all_summary_records.append({
            'values': {
                '日期': [{'type':'text','text': f'{start.isoformat()}~{end.isoformat()}'}],
                '店铺名称': [{'type':'text','text': store['store_name']}],
                '店铺代号': [{'type':'text','text': store['store_code']}],
                '广告总花费': round(total_expense,2),
                '总销售额': round(total_revenue,2),
                '总订单数': int(total_orders),
                '总展现量': int(total_impr),
                '总点击量': int(total_clicks),
                '平均CTR': round(avg_ctr,2),
                '平均CPC': round(avg_cpc,2),
                '总加购数': int(total_carts),
                '平均加购转化率': round(avg_cart,2),
                '整体ACOS': round((total_expense/total_revenue*100) if total_revenue else 0, 2),
                '整体ROAS': round(roas_total,2),
                '高表现SKU数': high_count,
                '低表现SKU数': low_count,
                '零成交SKU数': zero_count,
                '风险等级': [{'text': risk}],
                '总体建议': [{'type':'text','text': summary_text}],
                '抓取时间': f'{end.isoformat()} 02:00:00'
            }
        })
        run_report.append({'store': store['store_name'], 'status': 'ok', 'campaigns': len(sku_campaigns), 'rows': len(product_rows)})
    except Exception as e:
        run_report.append({'store': store.get('store_name',''), 'status': 'error', 'error': str(e)[:200]})

out = {
    'summary_count': len(all_summary_records),
    'detail_count': len(all_detail_records),
    'alert_count': len(all_alert_records),
    'run_report': run_report,
    'detail_records': all_detail_records[:30],
    'summary_records': all_summary_records,
    'alert_records': all_alert_records[:30]
}
print(json.dumps(out, ensure_ascii=False, indent=2))
