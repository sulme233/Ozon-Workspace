import pandas as pd
import numpy as np
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---c48d099d-ff70-4e3c-8b44-2dd89f7fe361.xlsx'
raw = pd.read_excel(path, sheet_name='Statistics', header=None)
headers = raw.iloc[1].tolist()
df = raw.iloc[2:].copy()
df.columns = headers
num_cols = ['费用，₽','广告费用份额, %','销售额，₽','订单，个','CTR, %','展现量','点击次数','添加到购物车','添加到购物车的转化率， %','单笔费用，₽','每次点击成本，₽']
for c in num_cols:
    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

total_cost = df['费用，₽'].sum()
total_sales = df['销售额，₽'].sum()
total_orders = df['订单，个'].sum()
total_impr = df['展现量'].sum()
total_clicks = df['点击次数'].sum()
total_cart = df['添加到购物车'].sum()
ctr = total_clicks / total_impr * 100 if total_impr else 0
cvr = total_orders / total_clicks * 100 if total_clicks else 0
cart_rate = total_cart / total_clicks * 100 if total_clicks else 0
cpc = total_cost / total_clicks if total_clicks else 0
cpa = total_cost / total_orders if total_orders else 0
roas = total_sales / total_cost if total_cost else 0
print('TOTAL')
print({'cost': round(total_cost,2), 'sales': round(total_sales,2), 'orders': int(total_orders), 'impr': int(total_impr), 'clicks': int(total_clicks), 'cart': int(total_cart), 'ctr': round(ctr,2), 'cvr': round(cvr,2), 'cart_rate': round(cart_rate,2), 'cpc': round(cpc,2), 'cpa': round(cpa,2), 'roas': round(roas,2)})

roi = df.copy()
roi['ROAS'] = np.where(roi['费用，₽']>0, roi['销售额，₽']/roi['费用，₽'], 0)
print('\nTOP_COST')
print(df[['SKU','商品名称','费用，₽','销售额，₽','订单，个','点击次数','CTR, %','单笔费用，₽']].sort_values('费用，₽', ascending=False).to_string(index=False))
print('\nZERO_ORDER_SPEND')
print(df.loc[(df['订单，个']==0) & (df['费用，₽']>0), ['SKU','商品名称','费用，₽','点击次数','CTR, %','添加到购物车']].sort_values('费用，₽', ascending=False).to_string(index=False))
print('\nBEST_ROAS')
print(roi[['SKU','商品名称','费用，₽','销售额，₽','订单，个','ROAS','单笔费用，₽']].sort_values('ROAS', ascending=False).to_string(index=False))

union_raw = pd.read_excel(path, sheet_name='Union', header=None)
uh = union_raw.iloc[1].tolist()
udf = union_raw.iloc[2:].copy(); udf.columns = uh
for c in ['销售额，₽','订单，个']:
    udf[c] = pd.to_numeric(udf[c], errors='coerce').fillna(0)
print('\nUNION_BY_PROMO')
print(udf.groupby('促销中的 SKU', as_index=False)[['销售额，₽','订单，个']].sum().sort_values('销售额，₽', ascending=False).to_string(index=False))
