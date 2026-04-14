import pandas as pd
from pathlib import Path
import json
path = Path(r"C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---6c7c90b5-b042-4b51-81f0-bca34555a075.xlsx")
xl = pd.ExcelFile(path)
print('SHEETS:', json.dumps(xl.sheet_names, ensure_ascii=False))
for s in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=s)
    print(f"\n=== SHEET: {s} ===")
    print('shape', df.shape)
    print(df.head(10).to_json(force_ascii=False, orient='records'))
    print('COLUMNS:', json.dumps([str(c) for c in df.columns], ensure_ascii=False))
