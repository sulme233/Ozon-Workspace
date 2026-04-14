import pandas as pd
from pathlib import Path
import json
path = Path(r"C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---6c7c90b5-b042-4b51-81f0-bca34555a075.xlsx")

stats = pd.read_excel(path, sheet_name='Statistics')
stats.columns = ['SKU','商品名称','工具','投放位置','广告活动ID','费用','广告费用份额','销售额','订单','CTR','展现量','点击次数','加购','加购转化率','单笔费用','CPC']
stats = stats.iloc[1:].copy()
for c in ['SKU','广告活动ID','费用','广告费用份额','销售额','订单','CTR','展现量','点击次数','加购','加购转化率','单笔费用','CPC']:
    stats[c] = pd.to_numeric(stats[c], errors='coerce')
stats['ROAS'] = stats['销售额'] / stats['费用']
stats['转化率_点击到订单'] = stats['订单'] / stats['点击次数']
stats['CPM'] = stats['费用'] / stats['展现量'] * 1000
stats['客单价'] = stats['销售额'] / stats['订单']
stats['加购到下单率'] = stats['订单'] / stats['加购']

summary = {
    'sku_count': int(stats['SKU'].nunique()),
    'cost': float(stats['费用'].sum()),
    'revenue': float(stats['销售额'].sum()),
    'orders': float(stats['订单'].sum()),
    'impressions': float(stats['展现量'].sum()),
    'clicks': float(stats['点击次数'].sum()),
    'cart_adds': float(stats['加购'].sum()),
}
summary['overall_ctr'] = summary['clicks']/summary['impressions']
summary['overall_cpc'] = summary['cost']/summary['clicks']
summary['overall_cvr'] = summary['orders']/summary['clicks']
summary['overall_roas'] = summary['revenue']/summary['cost']
summary['avg_order_value'] = summary['revenue']/summary['orders']
summary['cart_rate'] = summary['cart_adds']/summary['clicks']
summary['cart_to_order_rate'] = summary['orders']/summary['cart_adds']

print('SUMMARY')
print(json.dumps(summary, ensure_ascii=False, indent=2))

print('\nTOP_BY_COST')
cols=['SKU','商品名称','费用','销售额','订单','ROAS','CTR','点击次数','转化率_点击到订单','加购','加购转化率','单笔费用','CPC']
print(stats.sort_values('费用', ascending=False)[cols].head(10).to_json(force_ascii=False, orient='records'))

print('\nTOP_BY_REVENUE')
print(stats.sort_values('销售额', ascending=False)[cols].head(10).to_json(force_ascii=False, orient='records'))

print('\nWORST_ROAS_MINCOST300')
print(stats[stats['费用']>=300].sort_values('ROAS', ascending=True)[cols].head(10).to_json(force_ascii=False, orient='records'))

print('\nZERO_ORDER_MINCOST300')
print(stats[(stats['费用']>=300)&(stats['订单']==0)][cols].sort_values('费用', ascending=False).to_json(force_ascii=False, orient='records'))

union = pd.read_excel(path, sheet_name='Union')
union.columns = ['促销SKU','促销商品名称','合并SKU','合并商品名称','销售额','订单']
union = union.iloc[1:].copy()
for c in ['促销SKU','合并SKU','销售额','订单']:
    union[c] = pd.to_numeric(union[c], errors='coerce')
print('\nUNION_SUMMARY')
print(json.dumps({
    'rows': len(union),
    'revenue': float(union['销售额'].sum()),
    'orders': float(union['订单'].sum())
}, ensure_ascii=False, indent=2))
print('\nUNION_BY_PROMO_SKU')
print(union.groupby(['促销SKU','促销商品名称'], dropna=False)[['销售额','订单']].sum().reset_index().sort_values('销售额', ascending=False).head(10).to_json(force_ascii=False, orient='records'))
