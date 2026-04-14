# Ozon API 可继续补充的功能

基于 `references/ozon_api/seller_api_zh.txt` 与 `references/ozon_api/performance_api_zh.txt`，当前项目还可以继续扩展这些能力。

## 优先级高

### 1. FBS 订单看板
- 参考接口：`/v3/posting/fbs/list`、`/v3/posting/fbs/unfulfilled/list`、`/v3/posting/fbs/get`
- 可做指标：待发货订单数、超时未处理订单、不同状态订单分布、法人预留订单
- 价值：把库存/仓库从静态样本提升到真实履约状态

### 2. 库存与价格联动分析
- 参考接口：`/v4/product/info/stocks`、`/v1/product/info/stocks-by-warehouse/fbs`、`/v5/product/info/prices`
- 可做指标：可售库存、预留库存、低库存 SKU、高库存低销 SKU、价格异常 SKU
- 价值：形成商品经营动作，而不只是店铺级汇总

### 3. 财务汇总增强
- 参考接口：`/v3/finance/transaction/list`、`/v3/finance/transaction/totals`、`/v1/finance/cash-flow-statement/list`
- 可做指标：周期交易总额、服务费总额、退款率、现金流变化
- 价值：把销售模块从粗略流水统计升级为更稳定的经营口径

### 4. 广告搜索词/短语分析
- 参考接口：`POST /api/client/statistics/phrases`
- 可做指标：高点击低转化搜索词、浪费词、优质词、品牌词与泛词效果对比
- 价值：广告模块从 campaign 层进一步下钻到优化动作层

## 优先级中

### 5. 广告出价与限额机会分析
- 参考接口：`GET /api/client/limits/list`、`POST /api/min/sku`
- 可做指标：当前 SKU 最低出价、预算上限、出价空间、预算瓶颈
- 价值：辅助广告放量和控成本

### 6. 商品信息完善度与审核异常
- 参考接口：`/v3/product/info/list`、`/v3/products/info/attributes`
- 可做指标：审核失败商品、缺图商品、缺属性商品、佣金高商品
- 价值：帮助找出转化差和无法销售的根因

### 7. 退货与售后分析
- 参考接口：`/v1/returns/list`、`/v2/returns/rfbs/list`
- 可做指标：退货数量、退货原因分布、店铺退货率、问题 SKU
- 价值：补齐售后维度

## 已适合接入网页看板的数据
- 广告花费、广告销售额、ROAS
- 店铺销售额、退款、服务费
- 仓库数量、库存样本、预留库存
- 风险标记、健康分、建议动作

## 建议的实施顺序
1. 先补 FBS 订单状态看板
2. 再补库存与价格联动分析
3. 再补广告搜索词分析
4. 最后补退货和更完整财务口径
