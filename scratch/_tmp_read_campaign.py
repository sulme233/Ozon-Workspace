import pandas as pd
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\campaign_expense---cffeee84-9bb2-487f-92c4-4e25a7e65aef.xlsx'
xl = pd.ExcelFile(path)
print('SHEETS', xl.sheet_names)
for s in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=s)
    print(f'\n=== {s} ===')
    print(df.head(15).to_string())
    print('\nCOLUMNS:', list(df.columns))
    print('SHAPE:', df.shape)
