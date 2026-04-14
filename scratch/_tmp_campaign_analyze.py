import pandas as pd
import numpy as np
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\campaign_expense---cffeee84-9bb2-487f-92c4-4e25a7e65aef.xlsx'
raw = pd.read_excel(path, sheet_name='Expense', header=None)
headers = raw.iloc[1].tolist()
df = raw.iloc[2:].copy()
df.columns = headers
for c in ['费用，₽','积分，₽']:
    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
df['应计日期'] = pd.to_datetime(df['应计日期'], errors='coerce')
print('TOTAL_COST', round(df['费用，₽'].sum(),2))
print('\nBY_CAMPAIGN')
by_campaign = df.groupby(['广告活动ID','广告活动名称','推广类型'], as_index=False)['费用，₽'].sum().sort_values('费用，₽', ascending=False)
print(by_campaign.to_string(index=False))
print('\nBY_TYPE')
print(df.groupby('推广类型', as_index=False)['费用，₽'].sum().sort_values('费用，₽', ascending=False).to_string(index=False))
print('\nBY_DATE')
print(df.groupby(df['应计日期'].dt.date, as_index=False)['费用，₽'].sum().sort_values('应计日期').to_string(index=False))
print('\nPIVOT')
pivot = df.pivot_table(index=df['应计日期'].dt.date, columns='广告活动名称', values='费用，₽', aggfunc='sum', fill_value=0)
print(pivot.to_string())
