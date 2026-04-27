from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import http.cookiejar
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
    fetch_warehouses,
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
    parser.add_argument('--admin-username', type=str, default=str(os.environ.get('OZON_ADMIN_USERNAME') or ''), help='Admin username for protected API smoke checks')
    parser.add_argument('--admin-password', type=str, default=str(os.environ.get('OZON_ADMIN_PASSWORD') or ''), help='Admin password for protected API smoke checks')
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
    opener: urllib.request.OpenerDirector | None = None,
) -> Any:
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = urllib.request.Request(url, method=method.upper(), headers=headers, data=data)
    active_opener = opener or urllib.request.build_opener()
    try:
        with active_opener.open(request, timeout=timeout) as response:
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


def wait_for_refresh_job(
    base_url: str,
    *,
    job_id: str,
    refresh_timeout: int,
    request_timeout: int,
) -> Dict[str, Any]:
    deadline = time.time() + refresh_timeout
    while time.time() < deadline:
        payload = request_json_http(
            'GET',
            f'{base_url}/api/refresh/status?job_id={urllib.parse.quote(job_id)}',
            timeout=request_timeout,
        )
        if not isinstance(payload, dict) or payload.get('status') != 'ok':
            raise RuntimeError(f'Failed to query refresh job status for {job_id}: {payload}')
        job = payload.get('job') if isinstance(payload.get('job'), dict) else {}
        status = str(job.get('status', '')).strip().lower()
        if status == 'ok':
            return job
        if status == 'error':
            raise RuntimeError(str(job.get('error') or f'refresh job {job_id} failed'))
        time.sleep(2)
    raise TimeoutError(f'refresh job timeout: {job_id}')


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
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

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
            if process.poll() is not None:
                add_check(
                    checks,
                    'serve_process',
                    started,
                    'error',
                    f'serve process exited unexpectedly with code {process.returncode}. Possible port conflict on {args.port}.',
                )
                return {'status': 'error', 'checks': checks, 'base_url': base_url}
        except Exception as exc:
            add_check(checks, 'health', started, 'error', str(exc))
            return {'status': 'error', 'checks': checks, 'base_url': base_url}

        started = time.time()
        try:
            auth_status = request_json_http('GET', f'{base_url}/api/auth/status', timeout=args.request_timeout, opener=opener)
            bootstrap = auth_status.get('bootstrap') if isinstance(auth_status, dict) else {}
            if isinstance(bootstrap, dict) and bootstrap.get('can_bootstrap') and args.admin_username and args.admin_password:
                request_json_http(
                    'POST',
                    f'{base_url}/api/auth/bootstrap',
                    timeout=args.request_timeout,
                    payload={'username': args.admin_username, 'password': args.admin_password},
                    opener=opener,
                )
            if args.admin_username and args.admin_password:
                request_json_http(
                    'POST',
                    f'{base_url}/api/auth/login',
                    timeout=args.request_timeout,
                    payload={'username': args.admin_username, 'password': args.admin_password},
                    opener=opener,
                )
                add_check(checks, 'auth_login', started, 'ok', f'user={args.admin_username}')
            else:
                add_check(checks, 'auth_login', started, 'warning', 'admin credentials not provided; protected APIs may fail')
        except Exception as exc:
            add_check(checks, 'auth_login', started, 'error', str(exc))
            all_ok = False

        if args.skip_refresh:
            checks.append({'name': 'refresh', 'status': 'skipped', 'elapsed_ms': 0, 'detail': 'skip_refresh=true'})
        else:
            started = time.time()
            try:
                refreshed = request_json_http('POST', f'{base_url}/api/refresh', timeout=args.refresh_timeout, payload={}, opener=opener)
                ok = False
                detail = ''
                if isinstance(refreshed, dict) and refreshed.get('status') == 'accepted':
                    job_id = str(refreshed.get('job_id') or '').strip()
                    if not job_id:
                        raise RuntimeError('refresh accepted but missing job_id')
                    job = wait_for_refresh_job(
                        base_url,
                        job_id=job_id,
                        refresh_timeout=args.refresh_timeout,
                        request_timeout=args.request_timeout,
                    )
                    ok = str(job.get('status', '')).lower() == 'ok'
                    detail = f'job_id={job_id}, generated_at={(job.get("result") or {}).get("generated_at", "")}'
                elif isinstance(refreshed, dict) and refreshed.get('status') == 'ok':
                    ok = True
                    detail = f"snapshot_id={refreshed.get('snapshot_id')}"
                else:
                    detail = f'unexpected response: {refreshed}'
                add_check(
                    checks,
                    'refresh',
                    started,
                    'ok' if ok else 'error',
                    detail,
                )
                all_ok = all_ok and ok
            except Exception as exc:
                detail = str(exc)
                if (not args.strict_refresh) and ('timed out' in detail.lower() or 'timeout' in detail.lower()):
                    add_check(checks, 'refresh', started, 'warning', detail)
                else:
                    add_check(checks, 'refresh', started, 'error', detail)
                    all_ok = False

        started = time.time()
        try:
            refresh_latest = request_json_http('GET', f'{base_url}/api/refresh/latest', timeout=args.request_timeout, opener=opener)
            ok = isinstance(refresh_latest, dict) and refresh_latest.get('status') == 'ok'
            job = refresh_latest.get('job') if isinstance(refresh_latest, dict) else None
            job_status = (job or {}).get('status') if isinstance(job, dict) else None
            add_check(checks, 'refresh_latest', started, 'ok' if ok else 'error', f'job_status={job_status}')
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'refresh_latest', started, 'error', str(exc))
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
            config_payload = request_json_http('GET', f'{base_url}/api/config', timeout=args.request_timeout, opener=opener)
            config = config_payload.get('config') if isinstance(config_payload, dict) else {}
            ok = isinstance(config_payload, dict) and config_payload.get('status') == 'ok' and isinstance(config, dict)
            detail = f"days={config.get('days')}, max_workers={config.get('max_workers')}"
            add_check(checks, 'config', started, 'ok' if ok else 'error', detail)
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'config', started, 'error', str(exc))
            all_ok = False

        started = time.time()
        try:
            stores_payload = request_json_http('GET', f'{base_url}/api/stores', timeout=args.request_timeout)
            stores = stores_payload.get('stores') if isinstance(stores_payload, dict) else []
            ok = isinstance(stores_payload, dict) and stores_payload.get('status') == 'ok' and isinstance(stores, list)
            add_check(checks, 'stores', started, 'ok' if ok else 'error', f'count={len(stores) if isinstance(stores, list) else 0}')
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'stores', started, 'error', str(exc))
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

        started = time.time()
        try:
            dashboard_latest = request_json_http(
                'GET',
                f'{base_url}/api/dashboard/latest',
                timeout=args.request_timeout,
            )
            dashboard_payload = dashboard_latest.get('payload') if isinstance(dashboard_latest, dict) else {}
            ok = isinstance(dashboard_latest, dict) and dashboard_latest.get('status') == 'ok' and isinstance(dashboard_payload, dict)
            detail = (
                f"snapshot_id={(dashboard_payload or {}).get('snapshot_id')}, "
                f"store_count={len((dashboard_payload or {}).get('results') or [])}"
            )
            add_check(checks, 'dashboard_latest', started, 'ok' if ok else 'error', detail)
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'dashboard_latest', started, 'error', str(exc))
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

        started = time.time()
        probe_store_filter = str(args.store or '').strip()
        if not probe_store_filter:
            probe_store_filter = store_code
        try:
            probe_payload = {
                'days': min(args.days, 3),
                'request_timeout': min(args.request_timeout, 30),
                'store_filter': probe_store_filter,
            }
            probe_result = request_json_http(
                'POST',
                f'{base_url}/api/ozon/probe',
                timeout=max(args.request_timeout, 30),
                payload=probe_payload,
                opener=opener,
            )
            ok = isinstance(probe_result, dict) and probe_result.get('status') == 'ok' and isinstance(probe_result.get('probe'), dict)
            probe = probe_result.get('probe') if isinstance(probe_result, dict) else {}
            detail = (
                f"probe_status={(probe or {}).get('status')}, "
                f"errors={len((probe or {}).get('errors') or [])}, "
                f"warnings={len((probe or {}).get('warnings') or [])}"
            )
            add_check(checks, 'ozon_probe_run', started, 'ok' if ok else 'error', detail)
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'ozon_probe_run', started, 'error', str(exc))
            all_ok = False

        started = time.time()
        try:
            probe_latest = request_json_http('GET', f'{base_url}/api/ozon/probe/latest', timeout=args.request_timeout, opener=opener)
            ok = isinstance(probe_latest, dict) and probe_latest.get('status') == 'ok'
            probe_status = ((probe_latest.get('probe') or {}) if isinstance(probe_latest, dict) else {}).get('status')
            add_check(checks, 'ozon_probe_latest', started, 'ok' if ok else 'error', f'probe_status={probe_status}')
            all_ok = all_ok and ok
        except Exception as exc:
            add_check(checks, 'ozon_probe_latest', started, 'error', str(exc))
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
        warehouses = fetch_warehouses(store, limit=100, timeout=args.request_timeout)
        add_check(checks, 'ozon_warehouses', started, 'ok', f'count={len(warehouses)}')
    except Exception as exc:
        add_check(checks, 'ozon_warehouses', started, 'error', str(exc))
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
