import pandas as pd, json
path = r'C:\Users\user_9nAJQ3l23\.qclaw\workspace\商品广告分析表_2026-03-30.xlsx'
df = pd.read_excel(path)
print(df.head(20).to_json(force_ascii=False, orient='records'))
