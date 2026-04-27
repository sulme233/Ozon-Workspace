# REQUIREMENTS

## Functional Requirements

- [P0] 提供统一 Web 控制面板，可在页面内查看状态并触发刷新（`/api/refresh`）、查询刷新状态（`/api/refresh/status`、`/api/refresh/latest`）。
- [P0] 提供配置管理接口（`GET/POST /api/config`），支持 days/store_filter/limit_campaigns/max_workers/include_details/keep_history/write_db/db_path。
- [P0] 提供健康与数据查询接口（`/api/health`、`/api/snapshots`、`/api/snapshots/latest`、`/api/stores/trend`、`/api/ozon-api/catalog`）。
- [P0] 支持 SQLite 落盘：刷新后保存快照与店铺指标，可通过 API 读取。
- [P0] 提供 Ozon 实时探测接口（`POST /api/ozon/probe`、`GET /api/ozon/probe/latest`），覆盖广告、价格、订单履约等只读检查。
- [P1] 广告分析流水线需兼容不同 CSV 表头（中/俄/英变体），并在“future interval”报错时自动回退到前一日窗口。
- [P1] 广告对象详情抓取支持并发（`--object-workers`），减少接口等待时间。
- [P1] 提供 smoke 命令对本地接口进行一键巡检，支持可选 Ozon 只读探针。
- [P2] 提供 API 文档映射与分组，便于后续扩展新功能。

## Non-Functional Requirements

- [P0] 可靠性：后台刷新使用异步作业模型，不阻塞主线程。
- [P0] 安全性：仅使用 Ozon 只读接口进行探测，不修改平台数据。
- [P1] 可观测性：接口返回统一 `status` 字段，并给出错误/告警信息。
- [P1] 性能：同店铺内对象抓取并发，跨店铺支持并行（`max_workers`）。
- [P1] 可维护性：关键路径具备单元测试，文档与实现保持一致。

## Acceptance Criteria

- [AC-P0-1] `python -m unittest discover -s tests -p "test_*.py" -v` 全部通过。
- [AC-P0-2] `python run_ozon.py api-smoke --skip-refresh --no-history` 返回 `status=ok`。
- [AC-P0-3] `python run_ozon.py smoke --no-history` 至少完成 health/config/snapshots/latest_snapshot/store_trend/catalog/probe_latest 检查；refresh 在超时时可降级 warning，不得崩溃。
- [AC-P0-4] `/api/ozon/probe` 可执行并返回结构化结果（checks/warnings/errors）。
- [AC-P0-5] SQLite 文件存在且 `snapshots`、`store_metrics` 能被查询。
- [AC-P1-1] Ozon 官方文档入口与关键端点映射写入 `docs/` 文档，便于后续二次开发。
