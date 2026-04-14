import pandas as pd
import numpy as np
order_path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\店铺订单详情_3月---65789525-9bd2-4653-bd48-82a5c232fc25.xlsx'
promo_path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\商品推广_分天数据_20260228至20260329---cd39f777-cfee-4128-9d99-1aa83cdd91b2.xlsx'
odf = pd.read_excel(order_path)
odf['商品id'] = odf['商品id'].astype(str)
for c in ['用户实付金额(元)']:
    odf[c] = pd.to_numeric(odf[c], errors='coerce').fillna(0)
odf['支付时间'] = pd.to_datetime(odf['支付时间'], errors='coerce')
refund_kw = odf['售后状态'].astype(str).str.contains('退款', na=False)
ord_paid_goods = odf[odf['支付时间'].notna() & ~odf['商品'].astype(str).str.contains('补收差价', na=False)].copy()
ord_prod = ord_paid_goods.groupby(['商品id','商品']).agg(店铺订单数=('订单号','count'), 店铺销售额=('用户实付金额(元)','sum')).reset_index()
refund_prod = odf[refund_kw].groupby(['商品id','商品']).agg(退款订单数=('订单号','count'), 退款涉及金额=('用户实付金额(元)','sum')).reset_index()
pdf = pd.read_excel(promo_path, sheet_name=1)
pdf['日期_dt'] = pd.to_datetime(pdf['日期'], errors='coerce')
pdf = pdf[pdf['日期_dt'].notna()].copy()
pdf['商品ID'] = pdf['商品ID'].astype(str)
num_cols = ['净成交花费(元)','净交易额(元)','净成交笔数','曝光量','点击量','直接净交易额(元)','间接净交易额(元)']
for c in num_cols:
    pdf[c] = pd.to_numeric(pdf[c], errors='coerce').fillna(0)
prod_promo = pdf.groupby(['商品ID','商品名称']).agg(广告花费=('净成交花费(元)','sum'), 广告净交易额=('净交易额(元)','sum'), 广告净成交笔数=('净成交笔数','sum'), 总曝光=('曝光量','sum'), 总点击=('点击量','sum'), 直接净交易额=('直接净交易额(元)','sum'), 间接净交易额=('间接净交易额(元)','sum')).reset_index()
prod_promo['广告净投产比'] = np.where(prod_promo['广告花费']>0, prod_promo['广告净交易额']/prod_promo['广告花费'], 0)
prod_promo = prod_promo.merge(ord_prod, left_on='商品ID', right_on='商品id', how='left').drop(columns=['商品id'], errors='ignore')
prod_promo = prod_promo.merge(refund_prod, left_on='商品ID', right_on='商品id', how='left', suffixes=('','_refund')).drop(columns=['商品id'], errors='ignore')
prod_promo = prod_promo.fillna(0)
prod_promo['广告销售占店铺销售比'] = np.where(prod_promo['店铺销售额']>0, prod_promo['广告净交易额']/prod_promo['店铺销售额']*100, 0)
print('TOP_PROMO_PRODUCTS')
print(prod_promo.sort_values('广告净交易额', ascending=False)[['商品ID','商品名称','广告花费','广告净交易额','广告净成交笔数','广告净投产比','直接净交易额','间接净交易额','店铺销售额','店铺订单数','广告销售占店铺销售比','退款订单数']].head(12).to_string(index=False))
print('\nLOW_EFFICIENCY_PROMO')
print(prod_promo[(prod_promo['广告花费']>50) & (prod_promo['广告净投产比']<4)].sort_values('广告花费', ascending=False)[['商品ID','商品名称','广告花费','广告净交易额','广告净成交笔数','广告净投产比','店铺销售额','退款订单数']].to_string(index=False))
