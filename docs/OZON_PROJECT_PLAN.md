# Ozon 多店铺经营分析系统优化推进方案

## 当前结论

项目已经完成了统一入口、广告/销售/订单/价格/物流/SKU 风险流水线和静态网页看板；
当前重点从“打通接口”转向“补齐商品级经营动作”和“整理项目结构”。

## 代码层优化方向

### 1. 统一公共库
新增 `ozon_lib.py`，集中处理：
- 配置读取
- 店铺遍历
- Seller API 请求头
- Performance token 获取
- 日期区间
- CSV 解析
- 俄文数字转换

目标：减少重复代码，方便后续把广告 / 销售 / 物流收束进一个主流程。

### 2. 模块成熟度判断

#### 广告模块
- 推荐作为第一条正式流水线
- 需要去掉前 10 个 campaign 限制
- 需要把规则阈值配置化
- 需要补失败重试和日志

#### 销售模块
- 当前基于 finance transaction 的口径过粗
- 需要确认真实经营指标口径：销售额、订单量、退款、服务费、SKU 维度

#### 物流/在途模块
- 当前主要拿到仓库、配送方式、库存样本
- 需要先明确业务要看的是：库存、发货中订单、在途货值、时效异常，还是其他指标

### 3. 正式主入口
当前已落地：
- `run_ozon_ads_pipeline.py`
- `run_ozon_sales_pipeline.py`
- `run_ozon_orders_pipeline.py`
- `run_ozon_pricing_pipeline.py`
- `run_ozon_sku_risk_pipeline.py`
- `run_ozon_logistics_pipeline.py`
- `run_ozon_daily_pipeline.py`
- `run_ozon_dashboard.py`

其中 `run_ozon_daily_pipeline.py` 负责串联多模块并输出经营总览。

## 本次已落地
- 新增 `ozon_lib.py`
- 新增 `analyze_ozon_project.py`
- 新增 `run_ozon.py`
- 新增 `run_ozon_ads_pipeline.py`
- 新增 `run_ozon_sales_pipeline.py`
- 新增 `run_ozon_orders_pipeline.py`
- 新增 `run_ozon_pricing_pipeline.py`
- 新增 `run_ozon_sku_risk_pipeline.py`
- 新增 `run_ozon_logistics_pipeline.py`
- 新增 `run_ozon_daily_pipeline.py`
- 新增 `run_ozon_dashboard.py`
- 调整 `run_ozon_pipeline_utf8.py`，统一转发到主入口
- 新增 `docs/PROJECT_FILE_MAP.md`
- 新增本说明文档

## 下一步建议
1. 完成低风险文件归档整理
2. 继续增强 SKU 风险明细的筛选、排序和导出
3. 继续细化商品级价格、库存、订单联动规则
4. 最后再评估企业微信落表与自动日报集成
