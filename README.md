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
python run_ozon.py list-stores
python run_ozon.py daily --days 7
python run_ozon.py ads --days 7 --store ozon_a
python run_ozon.py sales --days 14
python run_ozon.py orders --days 7
python run_ozon.py pricing --store ozon_g
python run_ozon.py sku-risk --reason 无可用库存 --sort-by free_stock --ascending
python run_ozon.py logistics --store 二店
python run_ozon.py dashboard --days 7
python run_ozon.py refresh --days 7
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
```

## 开发说明

- 所有主脚本现在统一做参数校验，错误会直接输出简洁信息，不再默认打印 traceback。
- HTTP 请求已经集中到 `ozon_lib.py`，便于后续继续加分页、缓存和更细的重试策略。
- 店铺筛选支持名称或店铺代码的部分匹配。

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
python -m unittest discover -s tests -p "test_*.py"
python run_ozon.py check-config
```
