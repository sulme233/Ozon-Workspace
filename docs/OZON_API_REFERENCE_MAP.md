# Ozon API Reference Map

This workspace keeps an internal API catalog in `ozon_api_catalog.py` and exposes it via:

- `GET /api/ozon-api/catalog?group=all`
- `GET /api/ozon-api/catalog?group=current`
- `GET /api/ozon-api/catalog?group=planned`

## Official documentation entry points

- Seller API intro (Chinese): <https://docs.ozon.ru/global/zh-hans/api/intro/>
- API documentation index: <https://docs.ozon.com/global/zh-hans/api/>
- Performance API (Chinese): <https://docs.ozon.com/global/zh-hans/api/perfomance-api/>

## Workspace source references

- `references/ozon_api/seller_api_zh.txt`
- `references/ozon_api/performance_api_zh.txt`
- `docs/API_FEATURE_OPPORTUNITIES.md`
- `docs/OZON_API_DEEP_DIVE.md`

## Endpoints currently wired in code

### Performance API

- `POST /api/client/token`
- `GET /api/client/campaign`
- `GET /api/client/campaign/{campaignId}/objects`
- `GET /api/client/statistics/campaign/product`

### Seller API

- `POST /v3/finance/transaction/list`
- `POST /v3/posting/fbs/list`
- `POST /v3/posting/fbs/unfulfilled/list`
- `POST /v5/product/info/prices`
- `POST /v2/warehouse/list`
- `POST /v2/delivery-method/list`
- `POST /v1/product/info/warehouse/stocks`

## Notes from docs sync

- Seller API intro examples still mention `POST /v1/warehouse/list`; current API change logs in local reference indicate migration to `POST /v2/warehouse/list`.
- Performance API references in local docs indicate host migration to `api-performance.ozon.ru` (old `performance.ozon.ru` deprecated).

## Planned high-value endpoints

- `POST /api/client/statistics/phrases`
- `POST /v3/posting/fbs/get`
- `POST /v4/product/info/stocks`
- `POST /v1/product/info/stocks-by-warehouse/fbs`
- `POST /v3/finance/transaction/totals`
- `POST /v1/finance/cash-flow-statement/list`
- `POST /v1/returns/list`
