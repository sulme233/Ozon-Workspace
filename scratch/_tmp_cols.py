import pandas as pd
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---c48d099d-ff70-4e3c-8b44-2dd89f7fe361.xlsx'
raw = pd.read_excel(path, sheet_name='Statistics', header=None)
print(raw.head(3).to_string())
print(list(raw.iloc[0]))
