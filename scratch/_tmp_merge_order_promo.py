import pandas as pd
import numpy as np
order_path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\店铺订单详情_3月---65789525-9bd2-4653-bd48-82a5c232fc25.xlsx'
promo_path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\商品推广_分天数据_20260228至20260329---cd39f777-cfee-4128-9d99-1aa83cdd91b2.xlsx'

odf = pd.read_excel(order_path)
for c in ['商品总价(元)','店铺优惠折扣(元)','平台优惠折扣(元)','用户实付金额(元)']:
    odf[c] = pd.to_numeric(odf[c], errors='coerce').fillna(0)
odf['支付时间'] = pd.to_datetime(odf['支付时间'], errors='coerce')
odf['日期'] = odf['支付时间'].dt.date
refund_kw = odf['售后状态'].astype(str).str.contains('退款', na=False)
ord_daily = odf[odf['支付时间'].notna()].groupby('日期').agg(店铺支付金额=('用户实付金额(元)','sum'), 店铺支付订单数=('订单号','count')).reset_index()
ord_paid_goods = odf[odf['支付时间'].notna() & ~odf['商品'].astype(str).str.contains('补收差价', na=False)].copy()
ord_prod = ord_paid_goods.groupby(['商品id','商品']).agg(店铺订单数=('订单号','count'), 店铺销售额=('用户实付金额(元)','sum')).reset_index()
refund_prod = odf[refund_kw].groupby(['商品id','商品']).agg(退款订单数=('订单号','count'), 退款涉及金额=('用户实付金额(元)','sum')).reset_index()

sdf = pd.read_excel(promo_path, sheet_name=0)
sdf['日期_dt'] = pd.to_datetime(sdf['日期'], errors='coerce')
sdf = sdf[sdf['日期_dt'].notna()].copy()
for c in ['净成交花费(元)','净交易额(元)','总花费(元)','净成交笔数','交易额(元)','成交笔数','曝光量','点击量']:
    sdf[c] = pd.to_numeric(sdf[c], errors='coerce').fillna(0)
sdf['日期'] = sdf['日期_dt'].dt.date
sum_daily = sdf[['日期','净成交花费(元)','净交易额(元)','净成交笔数','总花费(元)','曝光量','点击量']].copy()
merged = sum_daily.merge(ord_daily, on='日期', how='left').fillna(0)
merged['广告净投产比'] = np.where(merged['净成交花费(元)']>0, merged['净交易额(元)']/merged['净成交花费(元)'], 0)
merged['广告点击率'] = np.where(merged['曝光量']>0, merged['点击量']/merged['曝光量']*100, 0)
merged['广告CPC'] = np.where(merged['点击量']>0, merged['总花费(元)']/merged['点击量'], 0)
merged['广告单量占店铺支付比'] = np.where(merged['店铺支付订单数']>0, merged['净成交笔数']/merged['店铺支付订单数']*100, 0)
merged['广告销售额占店铺支付比'] = np.where(merged['店铺支付金额']>0, merged['净交易额(元)']/merged['店铺支付金额']*100, 0)
print('SUMMARY_ALL')
print({
 '广告净成交花费': round(merged['净成交花费(元)'].sum(),2),
 '广告净交易额': round(merged['净交易额(元)'].sum(),2),
 '广告净成交笔数': round(merged['净成交笔数'].sum(),2),
 '店铺支付金额': round(merged['店铺支付金额'].sum(),2),
 '店铺支付订单数': int(merged['店铺支付订单数'].sum()),
 '整体广告净投产比': round(merged['净交易额(元)'].sum()/merged['净成交花费(元)'].sum(),2),
 '广告销售额占店铺支付比': round(merged['净交易额(元)'].sum()/merged['店铺支付金额'].sum()*100,2),
 '广告订单占店铺支付比': round(merged['净成交笔数'].sum()/merged['店铺支付订单数'].sum()*100,2)
})
print('\nBEST_DAYS_BY_ROAS')
print(merged[['日期','净成交花费(元)','净交易额(元)','净成交笔数','店铺支付金额','广告净投产比','广告销售额占店铺支付比']].sort_values('广告净投产比', ascending=False).head(10).to_string(index=False))
print('\nWORST_DAYS_BY_ROAS')
print(merged[['日期','净成交花费(元)','净交易额(元)','净成交笔数','店铺支付金额','广告净投产比','广告销售额占店铺支付比']].sort_values('广告净投产比', ascending=True).head(10).to_string(index=False))

pdf = pd.read_excel(promo_path, sheet_name=1)
pdf['日期_dt'] = pd.to_datetime(pdf['日期'], errors='coerce')
pdf = pdf[pdf['日期_dt'].notna()].copy()
num_cols = ['净成交花费(元)','净交易额(元)','总花费(元)','净成交笔数','交易额(元)','成交笔数','曝光量','点击量','直接净交易额(元)','间接净交易额(元)','直接净成交笔数','间接净成交笔数']
for c in num_cols:
    pdf[c] = pd.to_numeric(pdf[c], errors='coerce').fillna(0)
prod_promo = pdf.groupby(['商品ID','商品名称']).agg(广告花费=('净成交花费(元)','sum'), 广告净交易额=('净交易额(元)','sum'), 广告净成交笔数=('净成交笔数','sum'), 总曝光=('曝光量','sum'), 总点击=('点击量','sum'), 直接净交易额=('直接净交易额(元)','sum'), 间接净交易额=('间接净交易额(元)','sum')).reset_index()
prod_promo['广告净投产比'] = np.where(prod_promo['广告花费']>0, prod_promo['广告净交易额']/prod_promo['广告花费'], 0)
prod_promo['CTR'] = np.where(prod_promo['总曝光']>0, prod_promo['总点击']/prod_promo['总曝光']*100, 0)
prod_promo['CPC'] = np.where(prod_promo['总点击']>0, prod_promo['广告花费']/prod_promo['总点击'], 0)
prod_promo = prod_promo.merge(ord_prod, left_on='商品ID', right_on='商品id', how='left').drop(columns=['商品id'], errors='ignore')
prod_promo = prod_promo.merge(refund_prod, left_on='商品ID', right_on='商品id', how='left', suffixes=('','_refund')).drop(columns=['商品id'], errors='ignore')
prod_promo = prod_promo.fillna(0)
prod_promo['广告销售占店铺销售比'] = np.where(prod_promo['店铺销售额']>0, prod_promo['广告净交易额']/prod_promo['店铺销售额']*100, 0)
print('\nTOP_PROMO_PRODUCTS')
print(prod_promo.sort_values('广告净交易额', ascending=False)[['商品ID','商品名称','广告花费','广告净交易额','广告净成交笔数','广告净投产比','店铺销售额','店铺订单数','广告销售占店铺销售比','退款订单数','退款涉及金额']].head(12).to_string(index=False))
print('\nLOW_EFFICIENCY_PROMO')
print(prod_promo[(prod_promo['广告花费']>50) & (prod_promo['广告净投产比']<4)].sort_values('广告花费', ascending=False)[['商品ID','商品名称','广告花费','广告净交易额','广告净成交笔数','广告净投产比','店铺销售额','退款订单数']].to_string(index=False))
