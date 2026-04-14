import pandas as pd
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\店铺订单详情_3月---65789525-9bd2-4653-bd48-82a5c232fc25.xlsx'
df = pd.read_excel(path)
df['商品数量(件)'] = pd.to_numeric(df['商品数量(件)'], errors='coerce')
print(df.sort_values('商品数量(件)', ascending=False)[['订单号','商品','商品数量(件)','支付时间','用户实付金额(元)']].head(10).to_string(index=False))
