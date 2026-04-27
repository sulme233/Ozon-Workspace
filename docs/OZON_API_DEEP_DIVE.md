# Ozon API Deep Dive

## Scope

This note summarizes the extra API depth added in this round for safer web-driven operations and faster troubleshooting.

## Newly leveraged behavior

### 1) Live probe now includes warehouse health

- Added `fetch_warehouses(...)` in `ozon_lib.py` using:
  - `POST /v2/warehouse/list`
- Added warehouse check in `run_ozon_dashboard.py::run_ozon_live_probe`:
  - `count`
  - `active_count`
  - `inactive_count`

Why it matters:
- Gives immediate infrastructure readiness signal (warehouse availability) before looking at orders or ads.
- Helps separate "traffic problem" from "fulfillment topology problem".

### 2) Local API smoke now covers full control loop

`run_ozon.py smoke` now validates:
- `GET /api/refresh/latest`
- `POST /api/ozon/probe`
- `GET /api/ozon/probe/latest`

Why it matters:
- Ensures web control plane checks both execution (`probe`) and persistence/readback (`probe/latest`, `refresh/latest`).

### 3) Standalone Ozon probe now includes warehouse endpoint

When using `--probe-ozon`, the direct Ozon read-only probe now checks:
- performance campaigns
- product prices
- warehouses
- FBS postings

## Next high-value read-only endpoints

1. `POST /api/client/statistics/phrases`
- Adds search phrase quality insights for ad optimization.

2. `POST /v3/posting/fbs/get`
- Enables posting-level diagnostics and fulfillment anomaly drill-down.

3. `POST /v4/product/info/stocks`
- Adds richer stock detail and stock-pressure indicators per SKU.

## Validation guidance

- Prefer `python run_ozon.py smoke --no-history` for full local API checks.
- Use `python run_ozon.py smoke --probe-ozon --ozon-store <code>` when you also need live upstream API evidence.
