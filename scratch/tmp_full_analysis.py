import pandas as pd, json, sys
sys.stdout.reconfigure(encoding='utf-8')
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---dc558f00-538d-47d2-b13c-227320c3c6f1.xlsx'

stats = pd.read_excel(path, sheet_name='Statistics', header=1)
union = pd.read_excel(path, sheet_name='Union', header=1)

stats = stats.rename(columns={
    '费用，₽':'cost','广告费用份额, %':'acos_pct','销售额，₽':'sales','订单，个':'orders',
    'CTR, %':'ctr','展现量':'impr','点击次数':'clicks','添加到购物车':'cart',
    '添加到购物车的转化率， %':'cart_rate','单笔费用，₽':'cost_per_order','每次点击成本，₽':'cpc',
    'SKU':'sku','商品名称':'name','工具':'tool','投放位置':'placement','广告活动 ID':'campaign_id'
})
union = union.rename(columns={
    '促销中的 SKU':'promo_sku','促销中的商品名称':'promo_name','合并卡中的 SKU':'union_sku',
    '组合卡中的商品名称':'union_name','销售额，₽':'union_sales','订单，个':'union_orders'
})

for c in ['cost','acos_pct','sales','orders','ctr','impr','clicks','cart','cart_rate','cost_per_order','cpc']:
    stats[c] = pd.to_numeric(stats[c], errors='coerce').fillna(0)
for c in ['union_sales','union_orders']:
    union[c] = pd.to_numeric(union[c], errors='coerce').fillna(0)

union_agg = union.groupby('promo_sku', dropna=False).agg({'union_sales':'sum','union_orders':'sum'}).reset_index()
res = stats.merge(union_agg, how='left', left_on='sku', right_on='promo_sku')
res['union_sales'] = res['union_sales'].fillna(0)
res['union_orders'] = res['union_orders'].fillna(0)
res['total_sales'] = res['sales'] + res['union_sales']
res['total_orders'] = res['orders'] + res['union_orders']
res['roas_direct'] = res.apply(lambda r: (r['sales']/r['cost']) if r['cost'] else 0, axis=1)
res['roas_total'] = res.apply(lambda r: (r['total_sales']/r['cost']) if r['cost'] else 0, axis=1)
res['zero_conversion'] = ((res['cost']>0) & (res['orders']==0))

# 简单分层

def classify(r):
    if r['cost'] == 0:
        return '未投放/无数据'
    if r['roas_total'] >= 8 and r['total_orders'] >= 3:
        return '强力放量'
    if r['roas_total'] >= 4 and r['total_orders'] >= 1:
        return '继续投放'
    if r['clicks'] >= 300 and r['orders'] == 0 and r['cart'] > 0:
        return '重点优化转化'
    if r['roas_total'] < 2 and r['cost'] > 1000:
        return '建议停投/重做'
    return '观察'

res['label'] = res.apply(classify, axis=1)

out = {
    'summary': {
        'sku_count': int(len(res)),
        'ad_cost': round(float(res['cost'].sum()), 2),
        'direct_sales': round(float(res['sales'].sum()), 2),
        'union_sales': round(float(res['union_sales'].sum()), 2),
        'total_sales': round(float(res['total_sales'].sum()), 2),
        'direct_orders': int(res['orders'].sum()),
        'union_orders': int(res['union_orders'].sum()),
        'total_orders': int(res['total_orders'].sum()),
        'overall_roas_direct': round(float(res['sales'].sum()/res['cost'].sum()), 2) if res['cost'].sum() else 0,
        'overall_roas_total': round(float(res['total_sales'].sum()/res['cost'].sum()), 2) if res['cost'].sum() else 0,
    },
    'top_by_total_sales': res.sort_values(['total_sales','sales'], ascending=False)[['sku','name','cost','sales','union_sales','total_sales','orders','union_orders','total_orders','roas_total','label']].head(10).fillna('').to_dict(orient='records'),
    'worst_by_roas_total': res[res['cost']>0].sort_values(['roas_total','cost'], ascending=[True,False])[['sku','name','cost','sales','union_sales','total_sales','orders','total_orders','clicks','cart','roas_total','label']].head(10).fillna('').to_dict(orient='records'),
    'zero_conversion': res[res['zero_conversion']].sort_values('cost', ascending=False)[['sku','name','cost','clicks','cart','ctr','cart_rate','label']].fillna('').to_dict(orient='records'),
    'full': res.sort_values(['total_sales','roas_total'], ascending=False)[['sku','name','cost','sales','union_sales','total_sales','orders','union_orders','total_orders','ctr','clicks','cart','cpc','roas_direct','roas_total','label']].fillna('').to_dict(orient='records')
}
print(json.dumps(out, ensure_ascii=False))
