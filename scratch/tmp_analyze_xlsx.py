import pandas as pd, json, sys
sys.stdout.reconfigure(encoding='utf-8')
path = r'C:\Users\user_9nAJQ3l23\.qclaw\media\inbound\推广分析_23.03.2026---dc558f00-538d-47d2-b13c-227320c3c6f1.xlsx'
xl = pd.ExcelFile(path)
out = {"sheets": xl.sheet_names}
preview = {}
for s in xl.sheet_names:
    df = pd.read_excel(path, sheet_name=s)
    preview[s] = {
        "shape": df.shape,
        "columns": [str(c) for c in df.columns.tolist()],
        "head": df.head(10).fillna('').astype(str).to_dict(orient='records')
    }
out['preview'] = preview
print(json.dumps(out, ensure_ascii=False))
