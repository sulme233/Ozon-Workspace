# Ozon Workspace

这个工作区现在按“统一入口 + 独立流水线 + 静态看板”组织，目标是让日常跑批、排错、看结果都走同一套路径。

## 核心入口

- `run_ozon.py`: 项目统一 CLI
- `run_ozon_ads_pipeline.py`: 广告分析
- `run_ozon_sales_pipeline.py`: 销售分析
- `run_ozon_orders_pipeline.py`: FBS 订单履约分析
- `run_ozon_pricing_pipeline.py`: 价格风险分析
- `run_ozon_sku_risk_pipeline.py`: SKU 风险分析
- `run_ozon_logistics_pipeline.py`: 仓储/物流分析
- `run_ozon_daily_pipeline.py`: 多模块汇总
- `run_ozon_dashboard.py`: 生成和服务 dashboard
- `ozon_lib.py`: 公共配置、鉴权、HTTP 请求、CLI 工具

## 常用命令

```bash
python run_ozon.py check-config
python run_ozon.py project-status
python run_ozon.py release-check --backup
python run_ozon.py list-stores
python run_ozon.py daily --days 7
python run_ozon.py daily --days 7 --max-workers 4
python run_ozon.py daily --days 7 --include-details
python run_ozon.py ads --days 7 --store ozon_a
python run_ozon.py ads --days 7 --store ozon_a --object-workers 8
python run_ozon.py sales --days 14
python run_ozon.py orders --days 7
python run_ozon.py pricing --store ozon_g
python run_ozon.py sku-risk --reason 无可用库存 --sort-by free_stock --ascending
python run_ozon.py logistics --store 二店
python run_ozon.py dashboard --days 7
python run_ozon.py dashboard --days 7 --max-workers 4
python run_ozon.py dashboard --days 7 --include-details
python run_ozon.py dashboard --days 7 --no-history
python run_ozon.py refresh --days 7
python run_ozon.py backup --name pre-release
python run_ozon.py restore backups/ozon_backup_YYYYMMDD_HHMMSS.zip --yes
```

也支持显式子命令形式：

```bash
python run_ozon.py run daily --days 7
python run_ozon.py run ads --days 7 --store ozon_a
```

## Dashboard

生成静态文件：

```bash
python run_ozon_dashboard.py --days 7
```

启动本地服务并支持页面内刷新：

```bash
python run_ozon_dashboard.py --serve --days 7
```

然后打开：

- `http://127.0.0.1:8765/index.html`

输出文件：

- `dashboard/index.html`
- `dashboard/data/latest.json`
- `dashboard/data/history/dashboard_YYYYMMDD_HHMMSS.json`

## 配置

默认配置文件：

- `secrets/ozon_accounts.json`

快速检查：

```bash
python scripts/inspect_ozon_config.py
python run_ozon.py check-config
python run_ozon.py project-status
```

`project-status` 会输出不会泄露密钥的项目健康摘要：配置就绪情况、验证/smoke/备份命令、部署文件存在性、受保护运行目录，以及当前已知本地工具问题。

发布或大改前优先运行 `python run_ozon.py release-check --backup`，它会先输出安全项目状态、执行本地验证，再创建运行数据备份；恢复时用 `python run_ozon.py restore <archive.zip> --yes`。`backup` / `restore` 也可以单独执行，统一转发到 `scripts/backup_runtime.py` / `scripts/restore_runtime.py`。

## 开发说明

- 所有主脚本现在统一做参数校验，错误会直接输出简洁信息，不再默认打印 traceback。
- HTTP 请求已经集中到 `ozon_lib.py`，便于后续继续加分页、缓存和更细的重试策略。
- 店铺筛选支持名称或店铺代码的部分匹配。
- Dashboard 后端已开始模块化：`dashboard_auth.py` 负责鉴权/登录限流，`dashboard_store_config.py` 负责店铺配置同步、版本和回滚，`dashboard_jobs.py` 负责刷新任务队列，`dashboard_probe.py` 负责实时 Ozon 探测，`run_ozon_dashboard.py` 保留服务入口和路由编排。
- Dashboard 前端已开始模块化：`dashboard_format.js` 负责格式化，`dashboard_api.js` 负责 API 请求与刷新轮询，`dashboard_state.js` 负责页面状态，`dashboard_render_admin.js` 负责后台管理渲染，`app.js` 保留经营看板主交互。

## 目录说明

- `docs/`: 项目文档
- `scripts/`: 配置检查和维护脚本
- `probes/`: 接口探测脚本
- `legacy/`: 历史原型脚本
- `scratch/`: 临时分析脚本
- `dashboard/`: 生成的看板和数据文件

## 验证

```bash
pip install -r requirements.txt
python scripts/validate.py
python run_ozon.py release-check --backup
python -m unittest discover -s tests -p "test_*.py"
python run_ozon.py check-config
```

推荐优先运行 `python scripts/validate.py`，它会统一执行单元测试、关键 Python 文件编译检查，并在本机安装 Node.js 时自动检查 `dashboard/*.js` 语法。

## Backend API & SQLite

- SQLite default path: `dashboard/data/ozon_metrics.db`
- Disable DB writes for one run: `--no-db`
- Override DB path: `--db-path C:/path/to/ozon_metrics.db`
- Skip history JSON snapshot files: `--no-history`

Serve mode with API:

```bash
python run_ozon_dashboard.py --serve --days 7 --max-workers 4
```

Available API endpoints:

- `GET /api/health`
- `GET /api/snapshots?limit=20`
- `GET /api/snapshots/latest?include_payload=0`
- `GET /api/stores/trend?store_code=ozon_a&limit=30`
- `GET /api/ozon-api/catalog?group=all`
- `GET /api/config`
- `POST /api/config`
- `GET /api/ozon/probe/latest`
- `POST /api/ozon/probe`
- `POST /api/refresh` (default async, returns `job_id`)
- `GET /api/refresh/status?job_id=1`
- `GET /api/refresh/latest`
- `POST /api/refresh?wait=1` (force sync)

Protected admin endpoints:

- `GET /api/auth/status`
- `POST /api/auth/bootstrap`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/admin/stores`
- `POST /api/admin/stores`
- `GET /api/admin/audit-logs`

Web-only control flow:

1. Start serve mode once: `python run_ozon_dashboard.py --serve --days 7`
2. Open `http://127.0.0.1:8765/index.html`
3. Use the control panel on page to edit runtime config and click refresh (no extra CLI per run).

## API Smoke Test

Use the unified command to validate local dashboard APIs end-to-end:

```bash
python run_ozon.py smoke --days 7 --max-workers 2
```

Optional: include read-only probes to key Ozon APIs for one store:

```bash
python run_ozon.py smoke --days 7 --probe-ozon --ozon-store ozon_a
```

Notes:

- `smoke` starts `run_ozon_dashboard.py --serve` internally, probes APIs, then stops the server automatically.
- `smoke` supports async refresh jobs (`POST /api/refresh` returning `accepted`) and will poll `/api/refresh/status`.
- Use `--no-history` and/or `--no-db` to avoid writing runtime artifacts during validation.
- Use `--skip-refresh` for quick API availability checks without triggering a full data refresh.
- Use `--strict-refresh` when you want refresh timeout to fail the smoke run.

## Deployment

This project is now deployable with environment-based runtime configuration.

Key env vars:

- `OZON_HOST`
- `OZON_PORT`
- `OZON_DB_PATH`
- `OZON_CONFIG_PATH`
- `OZON_ADMIN_USERNAME`
- `OZON_ADMIN_PASSWORD`

Quick start:

```bash
python run_ozon_dashboard.py --serve --host 0.0.0.0 --port 8765
```

Containerized start:

```bash
docker compose up -d --build
```

Full deployment instructions:

- `docs/DEPLOY.md`
