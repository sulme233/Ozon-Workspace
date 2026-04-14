# Ozon API Reference Map

This project keeps an internal API catalog in `ozon_api_catalog.py` and exposes it via:

- `GET /api/ozon-api/catalog?group=all`
- `GET /api/ozon-api/catalog?group=current`
- `GET /api/ozon-api/catalog?group=planned`

Primary source documents in workspace:

- `references/ozon_api/seller_api_zh.txt`
- `references/ozon_api/performance_api_zh.txt`
- `docs/API_FEATURE_OPPORTUNITIES.md`

Current endpoints already wired in pipelines:

- Performance API:
  - `POST /api/client/token`
  - `GET /api/client/campaign`
  - `GET /api/client/campaign/{campaignId}/objects`
  - `GET /api/client/statistics/campaign/product`
- Seller API:
  - `POST /v3/finance/transaction/list`
  - `POST /v3/posting/fbs/list`
  - `POST /v3/posting/fbs/unfulfilled/list`
  - `POST /v5/product/info/prices`
  - `POST /v2/warehouse/list`
  - `POST /v2/delivery-method/list`
  - `POST /v1/product/info/warehouse/stocks`

Planned/high-value endpoints (for next implementation rounds):

- `POST /api/client/statistics/phrases`
- `POST /v3/posting/fbs/get`
- `POST /v4/product/info/stocks`
- `POST /v1/product/info/stocks-by-warehouse/fbs`
- `POST /v3/finance/transaction/totals`
- `POST /v1/finance/cash-flow-statement/list`
- `POST /v1/returns/list`
