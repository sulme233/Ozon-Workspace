import pandas as pd
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\店铺订单详情_3月---65789525-9bd2-4653-bd48-82a5c232fc25.xlsx'
xl = pd.ExcelFile(path)
print('SHEETS', xl.sheet_names)
for s in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=s)
    print(f'\n=== {s} ===')
    print(df.head(12).to_string())
    print('\nCOLUMNS:', list(df.columns))
    print('SHAPE:', df.shape)
