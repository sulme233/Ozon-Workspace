from __future__ import annotations

import json
from pathlib import Path

FILES = [
    'legacy/run_all_stores_ads.py',
    'legacy/run_sales_phase1.py',
    'legacy/run_logistics_phase1.py',
    'legacy/run_intransit_value_phase2.py',
    'legacy/run_ad_analysis_store2.py',
    'legacy/run_ad_analysis_store2_deep.py',
    'scripts/check_ozon_keys.py',
    'scripts/check_ozon_performance_keys.py',
    'scripts/check_perf_tokens.py',
    'scripts/inspect_ozon_config.py',
]

SUMMARY = {
    'project': 'Ozon 多店铺经营分析系统',
    'current_focus': [
        '广告、销售、订单、价格、物流与 SKU 风险都已纳入正式流水线',
        '已具备统一主入口、网页看板和经营总览聚合能力',
        '当前更适合继续补商品级经营动作和目录归档整理',
        '部分历史脚本、探测脚本与临时脚本应迁入分类目录',
    ],
    'recommended_next_steps': [
        '完善 SKU 风险明细的筛选和排序能力',
        '继续补商品价格、库存、订单的联动规则',
        '完成 legacy/probes/scripts/scratch/docs 的物理归档',
        '再决定是否把正式主线迁入 pipelines/lib 目录',
    ],
    'files': FILES,
}

print(json.dumps(SUMMARY, ensure_ascii=False, indent=2))
