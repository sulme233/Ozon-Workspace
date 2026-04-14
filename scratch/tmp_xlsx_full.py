import pandas as pd
from pathlib import Path
path = Path(r"C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---6c7c90b5-b042-4b51-81f0-bca34555a075.xlsx")
stats = pd.read_excel(path, sheet_name='Statistics')
stats.columns = ['SKU','商品名称','工具','投放位置','广告活动ID','费用','广告费用份额','销售额','订单','CTR','展现量','点击次数','加购','加购转化率','单笔费用','CPC']
stats = stats.iloc[1:].copy()
for c in ['SKU','费用','销售额','订单','CTR','展现量','点击次数','加购','加购转化率','单笔费用','CPC']:
    stats[c] = pd.to_numeric(stats[c], errors='coerce')
stats['ROAS'] = stats['销售额'] / stats['费用']
stats['CVR'] = stats['订单'] / stats['点击次数']

print(stats[['SKU','商品名称','费用','销售额','订单','ROAS','CPC','CTR','点击次数','加购','加购转化率','CVR']].sort_values('SKU').to_json(force_ascii=False, orient='records'))
