# Ozon 多店铺经营系统项目总规划

## 1. 当前定位

本项目已经从“单脚本接口试验”升级为一个本地可部署的 Ozon 多店铺经营工作台。当前核心形态是：

- 统一 CLI 入口：`run_ozon.py`
- 多条独立业务流水线：广告、销售、FBS 订单履约、价格、SKU 风险、仓储/物流、每日汇总
- Web Dashboard：静态页面 + 本地 HTTP API + 页面内刷新
- SQLite 持久化：快照、店铺指标、后台账号、会话、审计日志、店铺配置版本
- 管理后台：登录、店铺配置同步、配置版本记录与回滚
- 部署骨架：`.env.example`、`Dockerfile`、`docker-compose.yml`、`docs/DEPLOY.md`

项目下一阶段的重点不再是“能不能跑”，而是把它变成稳定、可维护、可交付的日常经营工具。

## 2. 架构分层

### 2.1 入口层

- `run_ozon.py`：统一命令入口，转发到各条流水线、配置检查、项目健康摘要、发布前本地预检、smoke 测试和运行数据备份/恢复。
- `run_ozon_dashboard.py`：Dashboard 生成与本地服务入口，同时编排 API 路由。
- `scripts/validate.py`：项目质量门，负责单元测试、Python 编译检查和前端 JS 语法检查。

### 2.2 业务流水线层

- `run_ozon_ads_pipeline.py`：广告分析，含 CSV 口径兼容和对象详情抓取。
- `run_ozon_sales_pipeline.py`：销售/财务交易分析。
- `run_ozon_orders_pipeline.py`：FBS 订单履约分析。
- `run_ozon_pricing_pipeline.py`：价格风险分析。
- `run_ozon_sku_risk_pipeline.py`：SKU 风险分析。
- `run_ozon_logistics_pipeline.py`：仓储/物流分析。
- `run_ozon_daily_pipeline.py`：跨模块汇总，供 dashboard 使用。

### 2.3 公共能力层

- `ozon_lib.py`：配置、店铺选择、鉴权头、请求重试、分页、数字/日期工具和 Ozon API 封装。
- `ozon_db.py`：SQLite 表结构、快照、趋势、后台账号、会话、审计和店铺配置版本。
- `ozon_api_catalog.py`：本地 Ozon API 能力目录。

### 2.4 Dashboard 后端模块

- `dashboard_auth.py`：管理员初始化、登录限流、Cookie/Session 辅助。
- `dashboard_jobs.py`：异步刷新任务队列和刷新配置快照。
- `dashboard_probe.py`：Ozon 只读实时探测。
- `dashboard_store_config.py`：店铺配置读写、JSON/SQLite 同步、版本回滚。
- `run_ozon_dashboard.py`：保留服务入口、路由编排和页面生成。

### 2.5 Dashboard 前端模块

- `dashboard/index.html`：页面骨架。
- `dashboard/app.css`：视觉样式。
- `dashboard/app.js`：经营看板渲染与交互主逻辑。
- `dashboard/dashboard_api.js`：API 请求、刷新任务轮询。
- `dashboard/dashboard_state.js`：页面状态。
- `dashboard/dashboard_format.js`：格式化工具。
- `dashboard/dashboard_render_admin.js`：后台管理 UI 渲染。

### 2.6 运维与交付层

- `.env.example`：环境变量模板。
- `Dockerfile` / `docker-compose.yml`：容器化部署。
- `docs/DEPLOY.md`：部署、备份、恢复、反向代理和安全加固说明。
- `scripts/backup_runtime.py` / `scripts/restore_runtime.py`：运行数据备份恢复。
- `scripts/manage_admin.py`：后台管理员维护。
- `scripts/smoke_test_interfaces.py`：本地 API 端到端巡检。

## 3. 当前最高优先级

### P0：稳定性和安全边界

1. 所有 dashboard 管理接口必须走登录校验，公开接口只保留健康检查、只读数据和必要静态资源。
2. Ozon 实时探测保持只读，不做任何会修改平台数据的调用。
3. 刷新任务继续使用异步作业模型，避免长时间请求阻塞页面和服务线程。
4. SQLite、`ozon_accounts.json`、备份目录和部署密钥目录必须保持在 `.gitignore` / `.dockerignore` 保护范围内。
5. 每次重要改动至少通过 `python scripts/validate.py`；开始排查或交接前可先运行 `python run_ozon.py project-status` 获取安全健康摘要，发布或大改前优先运行 `python run_ozon.py release-check --backup`。

当前基线（2026-04-26）：`python scripts/validate.py` 已通过，覆盖 56+ 个单元测试、主 Python 文件编译检查，以及 dashboard JavaScript 语法检查。项目 OpenCode 配置已统一使用 `Cherry-plus/gpt-5.5` 作为 `model` 和 `small_model`，并限制启用 provider 为 `Cherry-plus`。全局 OhMyOpenAgent 的 explore、librarian、quick 与临时配置也已统一到 `Cherry-plus/gpt-5.5`；如果当前会话仍报旧模型，需要重启 OpenCode 会话加载新配置。统一 CLI 已新增 `project-status`，用于不泄露密钥地查看配置、验证、部署和本地工具状态。

### P1：经营动作闭环

1. 把 dashboard 的异常提示继续收敛成“今日动作清单”：广告有花费无订单、无价格、SKU 风险、待履约、低库存。
2. 为每个异常补充可追踪字段：店铺、模块、严重程度、建议动作、数据来源时间。
3. 增加导出能力：当前筛选店铺 / 当前动作清单导出为 CSV 或 JSON。（已完成前端动作清单导出，后续可扩展更多明细导出。）
4. 把 SKU、价格、库存、广告对象之间的关联做成统一商品维度视图。

### P2：工程可维护性

1. 继续拆分 `run_ozon_dashboard.py`：路由层、响应工具、服务启动可以进一步模块化。
2. 为新增模块补齐单元测试，尤其是认证、配置回滚、刷新任务状态机和前端 API 行为。
3. 引入更清晰的数据契约文档：dashboard payload、snapshot、store metrics、admin store view。
4. 建立发布前 checklist：验证、备份、部署、回滚、 smoke。

## 4. 近期迭代路线图

### 第 1 阶段：收口当前成果（当前优先）

- [x] 明确统一入口和 dashboard 服务入口。
- [x] 保留 SQLite 和后台管理能力。
- [x] 增加部署文档与容器化骨架。
- [x] 增加项目级验证脚本。
- [x] 将当前大批改动整理成一次可审阅的提交前状态：测试通过、文档同步、敏感文件不入库。
- [x] 补齐本地/容器忽略规则：`secrets/`、`deploy/data/`、`deploy/secrets/`、备份与部署 env 不进入仓库或镜像。
- [x] 处理协作环境配置：explore/librarian/quick 默认模型已统一到 `Cherry-plus/gpt-5.5`，当前运行中的旧会话如仍使用缓存需重启。

### 第 2 阶段：经营看板增强

- [x] 动作清单支持导出。
- [x] 店铺趋势增加更多指标：广告花费、ROAS、待履约、无价格商品、SKU 风险数。
- [ ] 商品维度汇总：价格、库存、订单、广告表现合并到同一 SKU/offer 视图。
- [ ] 增加 dashboard 空状态和错误状态的用户友好提示。

验收口径：完成一个 P1 功能前，至少新增对应单元测试；若改动涉及 API 或前端刷新流程，再运行 `python run_ozon.py api-smoke --skip-refresh --no-history`。

### 第 3 阶段：部署和运维硬化

- [x] 增加发布前备份提示和本地发布预检：`python run_ozon.py release-check --backup` 会执行安全项目状态、本地验证和运行数据备份；恢复统一走 `python run_ozon.py restore <archive.zip> --yes`。
- [ ] 增加 Docker Compose 生产示例，默认不直接暴露公网。
- [ ] 增加反向代理后 HTTPS/Cookie 配置检查。
- [ ] 增加数据库 schema 版本和迁移策略。

验收口径：部署相关改动必须同步更新 `.env.example`、`docs/DEPLOY.md` 和 smoke/backup/restore 命令示例；不得把真实凭据写入 `docker-compose.yml`。

### 第 4 阶段：自动化与外部集成

- [ ] 定时刷新与日报生成。
- [ ] 企业微信/邮件推送异常摘要。
- [ ] 更细粒度的权限模型：只读账号、运营账号、管理员账号。
- [ ] 可选接入远端对象存储保存历史快照和备份。

## 5. 验证策略

本项目的默认验证入口是：

```bash
python run_ozon.py project-status
python scripts/validate.py
```

它应覆盖：

- 单元测试：`python -m unittest discover -s tests -p "test_*.py"`
- Python 编译检查：主入口、公共库、dashboard 模块、运维脚本
- 前端语法检查：有 Node.js 时运行 `node --check dashboard/*.js`

涉及服务接口的改动再运行：

```bash
python run_ozon.py api-smoke --skip-refresh --no-history
python run_ozon.py smoke --days 2 --max-workers 1 --no-history
```

涉及真实 Ozon API 只读探测的改动再运行：

```bash
python run_ozon.py smoke --days 2 --skip-refresh --probe-ozon --ozon-store ozon_a --no-history
```

## 6. 风险清单

1. `run_ozon_dashboard.py` 仍然承担较多路由编排职责，后续继续增长会影响维护性。
2. 当前项目没有第三方 Web 框架，优点是部署轻，缺点是路由、中间件、CSRF 等需要自己维护。
3. Dashboard 前端已经拆出格式化、API、状态和后台管理渲染模块；`dashboard/app.js` 仍是较大的经营看板主交互文件，后续应继续按经营区域拆分。
4. 前端新增模块时必须确认 `render_html()` 已加载对应脚本，并由 `python scripts/validate.py` 自动纳入 `dashboard/*.js` 语法检查。
5. Ozon API 口径可能变化，必须保留 smoke 和 probe 作为回归检查。
6. 本地 SQLite 适合单机工作台；如果多用户并发和长期历史增长明显，需要重新评估数据库方案。

## 7. 文件治理原则

- 根目录只保留正式入口、公共库、部署入口和顶层文档。
- `docs/` 存放长期有效的规划、部署、API 和数据契约文档。
- `scripts/` 存放维护、验证、备份、迁移类脚本。
- `probes/` 存放接口探索脚本，不作为稳定入口。
- `legacy/` 存放历史原型，功能被正式流水线覆盖后再考虑归档或删除。
- `scratch/` 存放一次性分析脚本，不进入主流程。
