# TEST_RESULTS

## Environment

- Date: 2026-04-15
- Workspace: `C:/Users/666/Desktop/py/ozon-work`

## Executed Test Commands

1. `python -m unittest discover -s tests -p "test_*.py" -v`
- Result: PASS
- Summary: `Ran 35 tests in 0.123s, OK`

2. `python run_ozon.py api-smoke --days 2 --skip-refresh --request-timeout 20 --no-history`
- Result: PASS
- Covered APIs:
  - `GET /api/health`
  - `GET /api/refresh/latest`
  - `GET /api/snapshots`
  - `GET /api/config`
  - `GET /api/snapshots/latest`
  - `GET /api/stores/trend`
  - `GET /api/ozon-api/catalog`
  - `POST /api/ozon/probe`
  - `GET /api/ozon/probe/latest`

3. `python run_ozon.py smoke --days 2 --store ozon_a --limit-campaigns 8 --max-workers 1 --request-timeout 20 --refresh-timeout 300 --strict-refresh --no-history`
- Result: PASS
- Refresh check: async job completed (`job_id=1`, `job_status=ok`)

4. `python run_ozon.py smoke --days 2 --store ozon_a --skip-refresh --request-timeout 20 --no-history --probe-ozon --ozon-store ozon_a`
- Result: PASS
- Live Ozon probe checks:
  - performance campaigns
  - product prices
  - warehouses
  - FBS postings

5. `python run_ozon.py check-config`
- Result: PASS
- Summary: 9/9 stores enabled; seller and performance credentials ready for all stores.

## Failures Found and Resolution

- One transient failure was observed when two smoke commands were executed in parallel against the same port (`8765`), causing refresh status lookup inconsistency.
- Resolution: run smoke suites serially; added smoke-side process liveness check to catch serve-process anomalies earlier.

## Current Status

- All implemented tests and smoke checks are passing.
- No unresolved failing tests remain.
