import pandas as pd
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---c48d099d-ff70-4e3c-8b44-2dd89f7fe361.xlsx'
xl = pd.ExcelFile(path)
print('SHEETS', xl.sheet_names)
for s in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=s)
    print(f'\n=== {s} ===')
    print(df.head(20).to_string())
    print('\nCOLUMNS:', list(df.columns))
    print('SHAPE:', df.shape)
