# 工作区文件分层建议

## 当前建议入口
- 统一入口：`run_ozon.py`
- 兼容入口：`run_ozon_pipeline_utf8.py`

## 1. 正式主线脚本
这些文件建议作为后续持续维护对象：
- `run_ozon.py`
- `ozon_lib.py`
- `run_ozon_ads_pipeline.py`
- `run_ozon_orders_pipeline.py`
- `run_ozon_pricing_pipeline.py`
- `run_ozon_sku_risk_pipeline.py`
- `run_ozon_logistics_pipeline.py`
- `run_ozon_sales_pipeline.py`
- `run_ozon_daily_pipeline.py`
- `run_ozon_dashboard.py`
- `run_ozon_pipeline_utf8.py`
- `docs/ozon_system_progress.md`
- `docs/OZON_PROJECT_PLAN.md`

## 2. 现有主业务原型脚本
这些文件是现有成果来源，短期内不建议删除，但应逐步被正式入口替代：
- `legacy/run_all_stores_ads.py`
- `legacy/run_sales_phase1.py`
- `legacy/run_logistics_phase1.py`
- `legacy/run_intransit_value_phase2.py`
- `legacy/run_ad_analysis_store2.py`
- `legacy/run_ad_analysis_store2_deep.py`

## 3. 配置/凭据检查脚本
- `scripts/inspect_ozon_config.py`
- `scripts/check_ozon_keys.py`
- `scripts/check_ozon_performance_keys.py`
- `scripts/check_perf_tokens.py`
- `scripts/detect_store_currency.py`
- `scripts/upgrade_ozon_config_v2.py`
- `scripts/migrate_perf_secret.py`
- `scripts/update_ozon_enabled.py`
- `scripts/analyze_ozon_project.py`

## 4. 探测/试错脚本
这些文件更像接口摸索记录：
- `probes/probe_intransit_endpoints.py`
- `probes/probe_intransit_with_delivery.py`
- `probes/probe_logistics_deeper.py`
- `probes/try_perf_endpoints.py`
- `probes/try_statistics_payloads.py`
- `probes/check_one_ozon_store.py`

## 5. 临时脚本
这些已集中迁到临时目录：
- `scratch/tmp_*.py`
- `scratch/_tmp_*.py`

## 6. 当前目录整理建议
- 根目录保留：`run_ozon.py`、`run_ozon_pipeline_utf8.py`、`run_ozon_*_pipeline.py`、`ozon_lib.py`、`README.md`
- `docs/`：方案、进度、能力清单
- `scripts/`：配置维护脚本
- `probes/`：接口探测脚本
- `legacy/`：历史原型脚本
- `scratch/`：临时分析脚本

## 7. 后续可能的进一步重构
- `pipelines/`：正式入口实现
- `lib/`：公共库
- 当导入关系稳定后，再从根目录迁出正式主线代码
