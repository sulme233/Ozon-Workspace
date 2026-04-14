from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


WORKSPACE = Path(__file__).resolve().parents[1]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from ozon_lib import (
    OzonApiError,
    OzonConfigError,
    cli_error,
    fetch_fbs_postings,
    fetch_perf_campaigns,
    fetch_product_prices,
    load_config,
    print_json,
    require_non_negative_int,
    require_positive_int,
    select_stores,
    today_range,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Smoke test local dashboard APIs and optional Ozon APIs')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Dashboard host')
    parser.add_argument('--port', type=int, default=8765, help='Dashboard port')
    parser.add_argument('--days', type=int, default=7, help='Rolling day window')
    parser.add_argument('--store', type=str, default='', help='Store filter passed to dashboard service')
    parser.add_argument('--limit-campaigns', type=int, default=0, help='Limit campaigns per store, 0 means no limit')
    parser.add_argument('--max-workers', type=int, default=2, help='Store-level parallel workers')
    parser.add_argument('--include-details', action='store_true', help='Keep full details in refresh payload')
    parser.add_argument('--no-history', action='store_true', help='Do not write history snapshot while probing')
    parser.add_argument('--no-db', action='store_true', help='Do not persist snapshots into SQLite while probing')
    parser.add_argument('--db-path', type=str, default='', help='SQLite file path override')
    parser.add_argument('--startup-timeout', type=int, default=60, help='Seconds to wait for /api/health')
    parser.add_argument('--request-timeout', type=int, default=120, help='Seconds per API request')
    parser.add_argument('--refresh-timeout', type=int, default=300, help='Seconds to wait for /api/refresh')
    parser.add_argument('--skip-refresh', action='store_true', help='Skip /api/refresh call')
    parser.add_argument('--strict-refresh', action='store_true', help='Fail smoke test when refresh times out')
    parser.add_argument('--probe-ozon', action='store_true', help='Also probe key read-only Ozon endpoints')
    parser.add_argument('--ozon-store', type=str, default='', help='Store filter for Ozon endpoint probes')
    return parser


def build_serve_command(args: argparse.Namespace) -> List[str]:
    cmd = [
        sys.executable,
        str(WORKSPACE / 'run_ozon_dashboard.py'),
        '--serve',
        '--host',
        args.host,
        '--port',
        str(args.port),
        '--days',
        str(args.days),
        '--max-workers',
        str(args.max_workers),
    ]
    if args.store:
        cmd.extend(['--store', args.store])
    if args.limit_campaigns:
        cmd.extend(['--limit-campaigns', str(args.limit_campaigns)])
    if args.include_details:
        cmd.append('--include-details')
    if args.no_history:
        cmd.append('--no-history')
    if args.no_db:
        cmd.append('--no-db')
    if args.db_path:
        cmd.extend(['--db-path', args.db_path])
    return cmd


def request_json_http(
    method: str,
    url: str,
    *,
    timeout: int,
    payload: Dict[str, Any] | None = None,
) -> Any:
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, method=method.upper(), headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8', errors='replace')
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'HTTP {exc.code} for {url}: {body[:200]}') from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f'URL error for {url}: {exc.reason}') from exc


def wait_for_health(base_url: str, *, startup_timeout: int, request_timeout: int) -> Dict[str, Any]:
    deadline = time.time() + startup_timeout
    last_error = ''
    while time.time() < deadline:
        try:
            payload = request_json_http('GET', f'{base_url}/api/health', timeout=request_timeout)
            if isinstance(payload, dict) and payload.get('status') == 'ok':
                return payload
            last_error = f'Unexpected /api/health payload: {payload}'
        except Exception as exc:  # pragma: no cover - depends on startup race
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f'/api/health did not become ready in {startup_timeout}s: {last_error}')


def add_check(results: List[Dict[str, Any]], name: str, started: float, status: str, detail: str) -> None:
    results.append(
        {
            'name': name,
            'status': status,
            'elapsed_ms': int((time.time() - started) * 1000),
            'detail': detail,
        }
    )


def extract_first_store_code(latest_snapshot: Dict[str, Any] | None) -> str:
    if not latest_snapshot:
        return ''
    payload = latest_snapshot.get('payload') if isinstance(latest_snapshot, dict) else None
    if not isinstance(payload, dict):
        return ''
    results = payload.get('results') if isinstance(payload, dict) else []
    if not isinstance(results, list):
        return ''
    for item in results:
        if isinstance(item, dict):
            code = str(item.get('store_code', '')).strip()
            if code:
                return code
    return ''


def run_local_smoke(args: argparse.Namespace) -> Dict[str, Any]:
    base_url = f'http://{args.host}:{args.port}'
    checks: List[Dict[str, Any]] = []
    process: subprocess.Popen[str] | None = None
    all_ok = True

    try:
        process = subprocess.Popen(
            build_serve_command(args),
            cwd=str(WORKSPACE),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        started = time.time()
        try:
            health = wait_for_health(
                base_url,
                startup_timeout=args.startup_timeout,
                request_timeout=args.request_timeout,
            )
            add_check(checks, 'health', started, 'ok', f"db_path={health.get('db_path', '')}")
        except Exception as exc:
            add_check(checks, 'health', started, 'error', str(exc))
            return {'status': 'error', 'checks': checks, 'base_url': base_url}

        if args.skip_refresh:
            checks.append({'name': 'refresh', 'status': 'skipped', 'elapsed_ms': 0, 'detail': 'skip_refresh=true'})
        else:
            started = time.time()
            try:
                refreshed = request_json_http('POST', f'{base_url}/api/refresh', timeout=args.refresh_timeout, payload={})
                ok = isinstance(refreshed, dict) and refreshed.get('status') == 'ok'
                add_check(
                    checks,
                    'refresh',
                    started,
                    'ok' if ok else 'error',
                    f"snapshot_id={refreshed.get('snapshot_id') if isinstance(refreshed, dict) else ''}",
                )
                all_ok = all_ok and ok
            except Exception as exc:
                detail = str(exc)
                if (not args.strict_refresh) and 'timed out' in detail.lower():
                    add_check(checks, 'refresh', started, 'warning', detail)
                else:
                    add_check(checks, 'refresh', started, 'error', detail)
                    all_ok = False

        started = time.time()
        latest_snapshot: Dict[str, Any] | None = None
        try:
            snapshots = request_json_http('GET', f'{base_url}/api/snapshots?limit=5', timeout=args.request_timeout)
            count = len((snapshots or {}).get('snapshots', [])) if isinstance(snapshots, dict) else 0
            ok = isinstance(snapshots, dict) and snapshots.get('status') == 'ok'
            add_check(checks, 'snapshots', started, 'ok' if ok else 'error', f'count={count}')
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'snapshots', started, 'error', str(exc))
            all_ok = False

        started = time.time()
        try:
            latest = request_json_http(
                'GET',
                f'{base_url}/api/snapshots/latest?include_payload=1',
                timeout=args.request_timeout,
            )
            latest_snapshot = latest.get('snapshot') if isinstance(latest, dict) else None
            ok = isinstance(latest, dict) and latest.get('status') == 'ok'
            add_check(
                checks,
                'latest_snapshot',
                started,
                'ok' if ok else 'error',
                f"generated_at={(latest_snapshot or {}).get('generated_at', '')}",
            )
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'latest_snapshot', started, 'error', str(exc))
            all_ok = False

        store_code = extract_first_store_code(latest_snapshot)
        if store_code:
            started = time.time()
            try:
                trend = request_json_http(
                    'GET',
                    f'{base_url}/api/stores/trend?store_code={urllib.parse.quote(store_code)}&limit=10',
                    timeout=args.request_timeout,
                )
                points = len((trend or {}).get('points', [])) if isinstance(trend, dict) else 0
                ok = isinstance(trend, dict) and trend.get('status') == 'ok'
                add_check(checks, 'store_trend', started, 'ok' if ok else 'error', f'store_code={store_code}, points={points}')
                all_ok = all_ok and ok
            except Exception as exc:
                add_check(checks, 'store_trend', started, 'error', str(exc))
                all_ok = False
        else:
            checks.append({'name': 'store_trend', 'status': 'skipped', 'elapsed_ms': 0, 'detail': 'no store_code in latest snapshot'})

        started = time.time()
        try:
            catalog = request_json_http('GET', f'{base_url}/api/ozon-api/catalog?group=all', timeout=args.request_timeout)
            total = ((catalog or {}).get('catalog') or {}).get('total_count', 0) if isinstance(catalog, dict) else 0
            ok = isinstance(catalog, dict) and catalog.get('status') == 'ok' and int(total) >= 1
            add_check(checks, 'ozon_api_catalog', started, 'ok' if ok else 'error', f'total_count={total}')
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'ozon_api_catalog', started, 'error', str(exc))
            all_ok = False
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - unlikely
                process.kill()
                process.wait(timeout=10)

    return {'status': 'ok' if all_ok else 'error', 'checks': checks, 'base_url': base_url}


def run_ozon_probe(args: argparse.Namespace) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    all_ok = True

    config = load_config()
    filter_text = (args.ozon_store or args.store or '').strip()
    stores = select_stores(config, filter_text)
    store = stores[0]
    store_code = str(store.get('store_code', '')).strip()
    store_name = str(store.get('store_name', '')).strip()

    started = time.time()
    try:
        campaigns = fetch_perf_campaigns(store, timeout=args.request_timeout)
        add_check(checks, 'ozon_perf_campaigns', started, 'ok', f'count={len(campaigns)}')
    except Exception as exc:
        add_check(checks, 'ozon_perf_campaigns', started, 'error', str(exc))
        all_ok = False

    started = time.time()
    try:
        prices = fetch_product_prices(store, limit=5, timeout=args.request_timeout)
        add_check(checks, 'ozon_product_prices', started, 'ok', f'count={len(prices)}')
    except Exception as exc:
        add_check(checks, 'ozon_product_prices', started, 'error', str(exc))
        all_ok = False

    started = time.time()
    try:
        start_day, end_day = today_range(days=args.days)
        postings = fetch_fbs_postings(
            store,
            since=f'{start_day.isoformat()}T00:00:00Z',
            to=f'{end_day.isoformat()}T23:59:59Z',
            statuses=[],
            limit=5,
            timeout=args.request_timeout,
        )
        add_check(checks, 'ozon_fbs_postings', started, 'ok', f'count={len(postings)}')
    except Exception as exc:
        add_check(checks, 'ozon_fbs_postings', started, 'error', str(exc))
        all_ok = False

    return {
        'status': 'ok' if all_ok else 'error',
        'store_name': store_name,
        'store_code': store_code,
        'checks': checks,
    }


def main() -> None:
    try:
        args = build_parser().parse_args()
        require_positive_int(args.port, field='port')
        require_positive_int(args.days, field='days')
        require_non_negative_int(args.limit_campaigns, field='limit_campaigns')
        require_positive_int(args.max_workers, field='max_workers')
        require_positive_int(args.startup_timeout, field='startup_timeout')
        require_positive_int(args.request_timeout, field='request_timeout')
        require_positive_int(args.refresh_timeout, field='refresh_timeout')

        local_result = run_local_smoke(args)
        ozon_result: Dict[str, Any] | None = None
        final_status = local_result.get('status') == 'ok'

        if args.probe_ozon:
            ozon_result = run_ozon_probe(args)
            final_status = final_status and ozon_result.get('status') == 'ok'

        output = {
            'status': 'ok' if final_status else 'error',
            'local': local_result,
            'ozon': ozon_result,
        }
        print_json(output)

        if not final_status:
            raise SystemExit(1)
    except (OzonConfigError, OzonApiError, RuntimeError) as exc:
        cli_error(exc)


if __name__ == '__main__':
    main()
