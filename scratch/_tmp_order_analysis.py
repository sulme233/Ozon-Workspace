import pandas as pd
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\店铺订单详情_3月---65789525-9bd2-4653-bd48-82a5c232fc25.xlsx'
df = pd.read_excel(path)
for c in ['商品数量(件)','商品总价(元)','店铺优惠折扣(元)','平台优惠折扣(元)','用户实付金额(元)']:
    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
df['支付时间'] = pd.to_datetime(df['支付时间'], errors='coerce')

print('TOTAL_ROWS', len(df))
print('TOTAL_QTY', int(df['商品数量(件)'].sum()))
print('TOTAL_GMV', round(df['商品总价(元)'].sum(),2))
print('TOTAL_PAY', round(df['用户实付金额(元)'].sum(),2))
print('SHOP_DISC', round(df['店铺优惠折扣(元)'].sum(),2))
print('PLAT_DISC', round(df['平台优惠折扣(元)'].sum(),2))
print('AVG_PAY_PER_LINE', round(df['用户实付金额(元)'].mean(),2))

print('\nSTATUS')
status = df.groupby('订单状态').agg(订单数=('订单号','count'), 件数=('商品数量(件)','sum'), 实付=('用户实付金额(元)','sum')).sort_values('订单数', ascending=False)
print(status.to_string())

print('\nAFTERSALE')
after = df.groupby('售后状态').agg(订单数=('订单号','count'), 实付=('用户实付金额(元)','sum')).sort_values('订单数', ascending=False)
print(after.to_string())

print('\nTOP_PRODUCTS_BY_PAY')
prod = df.groupby(['商品id','商品']).agg(订单数=('订单号','count'), 件数=('商品数量(件)','sum'), 实付=('用户实付金额(元)','sum')).reset_index().sort_values('实付', ascending=False)
print(prod.head(12).to_string(index=False))

print('\nTOP_PRODUCTS_BY_ORDERS')
print(prod.sort_values(['订单数','实付'], ascending=[False,False]).head(12).to_string(index=False))

paid = df[df['支付时间'].notna()].copy()
paid['日期'] = paid['支付时间'].dt.date
print('\nDAILY_PAID')
daily = paid.groupby('日期').agg(支付订单数=('订单号','count'), 支付件数=('商品数量(件)','sum'), 支付金额=('用户实付金额(元)','sum')).reset_index().sort_values('日期')
print(daily.to_string(index=False))

print('\nUNPAID_COUNT', len(df[df['支付时间'].isna()]))
print('PAID_COUNT', len(paid))

print('\nPRICE_BANDS')
bands = pd.cut(df['用户实付金额(元)'], bins=[-0.01,0,50,100,200,500,1000,999999], labels=['0','0-50','50-100','100-200','200-500','500-1000','1000+'])
print(df.groupby(bands, observed=False).agg(订单数=('订单号','count'), 实付=('用户实付金额(元)','sum')).to_string())
