import pandas as pd
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\商品推广_分天数据_20260228至20260329---cd39f777-cfee-4128-9d99-1aa83cdd91b2.xlsx'
xl = pd.ExcelFile(path)
print('SHEETS', xl.sheet_names)
for s in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=s)
    print(f'\n=== {s} ===')
    print(df.head(12).to_string())
    print('\nCOLUMNS:', list(df.columns))
    print('SHAPE:', df.shape)
