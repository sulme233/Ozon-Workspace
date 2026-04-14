from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import socketserver
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

from ozon_lib import OzonConfigError, cli_error, load_config, print_json, require_non_negative_int, require_positive_int, select_stores
from ozon_api_catalog import get_ozon_api_catalog
from ozon_db import DEFAULT_DB_PATH, ensure_db, get_latest_snapshot, list_snapshots, list_store_trends, save_snapshot
from run_ozon_daily_pipeline import compact_store_results, merge_store_results


WORKSPACE = Path(__file__).resolve().parent
DASHBOARD_DIR = WORKSPACE / 'dashboard'
OUTPUT_FILE = DASHBOARD_DIR / 'index.html'
DATA_DIR = DASHBOARD_DIR / 'data'
LATEST_JSON_FILE = DATA_DIR / 'latest.json'
HISTORY_DIR = DATA_DIR / 'history'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Generate or serve the Ozon dashboard')
    parser.add_argument('--days', type=int, default=7, help='Rolling day window')
    parser.add_argument('--store', type=str, default='', help='Filter by store name or store code')
    parser.add_argument('--limit-campaigns', type=int, default=0, help='Limit campaigns per store, 0 means no limit')
    parser.add_argument('--max-workers', type=int, default=4, help='Store-level parallel workers')
    parser.add_argument('--include-details', action='store_true', help='Include full module details in dashboard data')
    parser.add_argument('--no-history', action='store_true', help='Do not write dashboard history snapshot')
    parser.add_argument('--db-path', type=str, default=str(DEFAULT_DB_PATH), help='SQLite path for dashboard snapshots')
    parser.add_argument('--no-db', action='store_true', help='Do not persist snapshots into SQLite')
    parser.add_argument('--serve', action='store_true', help='Serve dashboard locally and enable in-page refresh')
    parser.add_argument('--host', type=str, default='127.0.0.1', help='Dashboard host')
    parser.add_argument('--port', type=int, default=8765, help='Dashboard port')
    return parser


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    store_count = len(results)
    ok_count = len([item for item in results if item.get('status') == 'ok'])
    partial_count = len([item for item in results if item.get('status') == 'partial'])
    error_count = len([item for item in results if item.get('status') == 'error'])
    total_sales = sum(float((item.get('overview') or {}).get('sales_amount') or 0) for item in results)
    total_ad_expense = sum(float((item.get('overview') or {}).get('ad_expense_rub') or 0) for item in results)
    total_ad_revenue = sum(float((item.get('overview') or {}).get('ad_revenue_rub') or 0) for item in results)
    total_unfulfilled = sum(int((item.get('overview') or {}).get('unfulfilled_orders_count') or 0) for item in results)
    total_low_stock = sum(int((item.get('overview') or {}).get('low_stock_warehouses_count') or 0) for item in results)
    total_no_price = sum(int((item.get('overview') or {}).get('no_price_count') or 0) for item in results)
    total_risky_sku = sum(int((item.get('overview') or {}).get('risky_sku_count') or 0) for item in results)
    flagged_count = len([item for item in results if item.get('flags')])
    avg_health = round(sum(int(item.get('health_score') or 0) for item in results) / store_count, 1) if store_count else 0
    return {
        'store_count': store_count,
        'ok_count': ok_count,
        'partial_count': partial_count,
        'error_count': error_count,
        'flagged_count': flagged_count,
        'total_sales_amount': round(total_sales, 2),
        'total_ad_expense_rub': round(total_ad_expense, 2),
        'total_ad_revenue_rub': round(total_ad_revenue, 2),
        'total_unfulfilled_orders': total_unfulfilled,
        'total_low_stock_warehouses': total_low_stock,
        'total_no_price_items': total_no_price,
        'total_risky_skus': total_risky_sku,
        'overall_roas': round((total_ad_revenue / total_ad_expense), 2) if total_ad_expense else 0,
        'avg_health_score': avg_health,
    }


def collect_dashboard_payload(
    days: int,
    store_filter: str = '',
    limit_campaigns: int | None = None,
    max_workers: int = 4,
    include_details: bool = False,
) -> Dict[str, Any]:
    require_positive_int(days, field='days')
    require_positive_int(max_workers, field='max_workers')
    config = load_config()
    selected = select_stores(config, store_filter)
    results = merge_store_results(
        selected,
        days=days,
        limit_campaigns=limit_campaigns,
        max_workers=max_workers,
    )
    output_results = results if include_details else compact_store_results(results)
    generated_at = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return {
        'days': days,
        'store_filter': store_filter,
        'max_workers': max_workers,
        'include_details': bool(include_details),
        'generated_at': generated_at,
        'refresh_info': {
            'generated_at': generated_at,
            'store_count': len(output_results),
            'latest_json': str(LATEST_JSON_FILE),
        },
        'summary': build_summary(output_results),
        'results': output_results,
    }


def write_dashboard_files(payload: Dict[str, Any], keep_history: bool = True) -> Dict[str, str]:
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(render_html(payload), encoding='utf-8')
    LATEST_JSON_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    history_path = ''
    if keep_history:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        history_file = HISTORY_DIR / f'dashboard_{ts}.json'
        history_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        history_path = str(history_file)

    return {
        'html': str(OUTPUT_FILE),
        'latest_json': str(LATEST_JSON_FILE),
        'history_json': history_path,
    }


def _safe_json(payload: Dict[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=False)
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
    )


def render_html(payload: Dict[str, Any]) -> str:
    embedded = _safe_json(payload)
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ozon 多店铺经营看板</title>
  <link rel="stylesheet" href="./app.css">
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-top">
        <div class="hero-title">
          <div class="eyebrow">Unified Operations Dashboard</div>
          <h1>Ozon 多店铺经营看板</h1>
          <p id="hero-desc"></p>
        </div>
        <div class="toolbar">
          <button id="refresh-btn" class="btn primary" type="button">刷新最新数据</button>
          <button id="reload-btn" class="btn secondary" type="button">重新读取本地快照</button>
        </div>
      </div>
      <section class="hero-stats" id="hero-stats"></section>
      <div class="status-line" id="status-line">页面已加载当前快照。</div>
    </section>

    <section class="overview-grid" id="overview-grid"></section>
    <section class="board-grid" id="attention-grid"></section>
    <section class="board-grid" id="data-grid"></section>

    <section class="toolbar-card">
      <div class="toolbar-grid">
        <label class="field">
          <span class="field-label">搜索店铺</span>
          <input id="stores-search" class="input" type="search" placeholder="输入店铺名称、代号或风险关键词">
        </label>
        <label class="field">
          <span class="field-label">排序方式</span>
          <select id="sort-select" class="select">
            <option value="health-asc">按健康分从低到高</option>
            <option value="health-desc">按健康分从高到低</option>
            <option value="sales-desc">按销售额从高到低</option>
            <option value="risk-desc">按风险项从多到少</option>
            <option value="ads-desc">按广告花费从高到低</option>
          </select>
        </label>
        <div class="field">
          <span class="field-label">显示状态</span>
          <div class="filter-group" id="status-filter-group"></div>
        </div>
      </div>
      <div class="filter-row">
        <div class="filter-note" id="filter-note"></div>
        <div class="filter-note">建议优先处理健康分低、广告花费高且无单、SKU 风险集中的店铺。</div>
      </div>
    </section>

    <div class="section-head">
      <div>
        <h2>店铺经营态势</h2>
        <p>把销售、广告、订单、价格、库存和 SKU 风险放在同一张页面里，先看趋势，再看动作清单。</p>
      </div>
    </div>
    <section class="stores" id="stores"></section>
    <div class="footer" id="footer-text"></div>
  </main>

  <script id="embedded-payload" type="application/json">__EMBEDDED__</script>
  <script src="./app.js"></script>
</body>
</html>
""".replace('__EMBEDDED__', embedded)


def refresh_dashboard(
    days: int,
    store_filter: str = '',
    limit_campaigns: int | None = None,
    max_workers: int = 4,
    include_details: bool = False,
    keep_history: bool = True,
    write_db: bool = True,
    db_path: str = str(DEFAULT_DB_PATH),
) -> Dict[str, Any]:
    payload = collect_dashboard_payload(
        days=days,
        store_filter=store_filter,
        limit_campaigns=limit_campaigns,
        max_workers=max_workers,
        include_details=include_details,
    )
    files = write_dashboard_files(payload, keep_history=keep_history)
    snapshot_id: int | None = None
    resolved_db_path = db_path
    if write_db:
        resolved_db_path = ensure_db(db_path)
        snapshot_id = save_snapshot(payload, db_path=resolved_db_path)
    return {
        'status': 'ok',
        'output': files['html'],
        'latest_json': files['latest_json'],
        'history_json': files['history_json'],
        'store_count': len(payload.get('results', [])),
        'max_workers': max_workers,
        'include_details': bool(include_details),
        'keep_history': bool(keep_history),
        'write_db': bool(write_db),
        'db_path': resolved_db_path,
        'snapshot_id': snapshot_id,
        'generated_at': payload.get('generated_at'),
    }


def serve_dashboard(
    host: str,
    port: int,
    days: int,
    store_filter: str = '',
    limit_campaigns: int | None = None,
    max_workers: int = 4,
    include_details: bool = False,
    keep_history: bool = True,
    write_db: bool = True,
    db_path: str = str(DEFAULT_DB_PATH),
) -> None:
    resolved_db_path = ensure_db(db_path)
    refresh_state: Dict[str, Any] = {
        'days': days,
        'store_filter': store_filter,
        'limit_campaigns': limit_campaigns,
        'max_workers': max_workers,
        'include_details': include_details,
        'keep_history': keep_history,
        'write_db': write_db,
        'db_path': resolved_db_path,
        'refresh_lock': threading.Lock(),
    }

    class DashboardHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        @staticmethod
        def _query_int(query: Dict[str, List[str]], key: str, default: int, minimum: int, maximum: int) -> int:
            raw = (query.get(key) or [str(default)])[0]
            try:
                value = int(raw)
            except Exception:
                value = default
            return min(max(value, minimum), maximum)

        @staticmethod
        def _query_bool(query: Dict[str, List[str]], key: str, default: bool = False) -> bool:
            raw = (query.get(key) or ['1' if default else '0'])[0].strip().lower()
            return raw in {'1', 'true', 'yes', 'y', 'on'}

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)

            if not parsed.path.startswith('/api/'):
                super().do_GET()
                return

            try:
                if parsed.path == '/api/health':
                    self._send_json(
                        200,
                        {
                            'status': 'ok',
                            'db_path': refresh_state['db_path'],
                            'write_db': bool(refresh_state['write_db']),
                        },
                    )
                    return

                if parsed.path == '/api/snapshots':
                    limit = self._query_int(query, 'limit', default=20, minimum=1, maximum=200)
                    snapshots = list_snapshots(limit=limit, db_path=refresh_state['db_path'])
                    self._send_json(200, {'status': 'ok', 'snapshots': snapshots})
                    return

                if parsed.path == '/api/snapshots/latest':
                    include_payload = self._query_bool(query, 'include_payload', default=False)
                    snapshot = get_latest_snapshot(
                        include_payload=include_payload,
                        db_path=refresh_state['db_path'],
                    )
                    self._send_json(200, {'status': 'ok', 'snapshot': snapshot})
                    return

                if parsed.path == '/api/stores/trend':
                    store_code = (query.get('store_code') or [''])[0].strip()
                    if not store_code:
                        self._send_json(400, {'status': 'error', 'error': 'store_code is required'})
                        return
                    limit = self._query_int(query, 'limit', default=30, minimum=1, maximum=365)
                    points = list_store_trends(store_code, limit=limit, db_path=refresh_state['db_path'])
                    self._send_json(
                        200,
                        {
                            'status': 'ok',
                            'store_code': store_code,
                            'points': points,
                        },
                    )
                    return

                if parsed.path == '/api/ozon-api/catalog':
                    group = (query.get('group') or ['all'])[0]
                    catalog = get_ozon_api_catalog(group=group)
                    self._send_json(200, {'status': 'ok', 'catalog': catalog})
                    return

                self._send_json(404, {'status': 'error', 'error': f'Unknown API path: {parsed.path}'})
            except Exception as exc:
                self._send_json(500, {'status': 'error', 'error': str(exc)})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != '/api/refresh':
                self._send_json(404, {'status': 'error', 'error': f'Unknown API path: {parsed.path}'})
                return

            with refresh_state['refresh_lock']:
                try:
                    result = refresh_dashboard(
                        days=refresh_state['days'],
                        store_filter=refresh_state['store_filter'],
                        limit_campaigns=refresh_state['limit_campaigns'],
                        max_workers=refresh_state['max_workers'],
                        include_details=refresh_state['include_details'],
                        keep_history=refresh_state['keep_history'],
                        write_db=refresh_state['write_db'],
                        db_path=refresh_state['db_path'],
                    )
                    self._send_json(200, result)
                except Exception as exc:
                    self._send_json(500, {'status': 'error', 'error': str(exc)})

        def log_message(self, format: str, *args: Any) -> None:
            return

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer((host, port), DashboardHandler) as httpd:
        print_json({
            'status': 'ok',
            'mode': 'serve',
            'url': f'http://{host}:{port}/index.html',
            'days': days,
            'store_filter': store_filter,
            'max_workers': max_workers,
            'include_details': bool(include_details),
            'keep_history': bool(keep_history),
            'write_db': bool(write_db),
            'db_path': resolved_db_path,
        })
        httpd.serve_forever()


def main() -> None:
    try:
        args = build_parser().parse_args()
        require_positive_int(args.days, field='days')
        require_non_negative_int(args.limit_campaigns, field='limit_campaigns')
        require_positive_int(args.max_workers, field='max_workers')
        store_filter = (args.store or '').strip()
        limit_campaigns = args.limit_campaigns or None
        keep_history = not args.no_history
        write_db = not args.no_db
        db_path = str(Path(args.db_path).expanduser())
        if args.serve:
            serve_dashboard(
                args.host,
                args.port,
                days=args.days,
                store_filter=store_filter,
                limit_campaigns=limit_campaigns,
                max_workers=args.max_workers,
                include_details=args.include_details,
                keep_history=keep_history,
                write_db=write_db,
                db_path=db_path,
            )
            return

        result = refresh_dashboard(
            days=args.days,
            store_filter=store_filter,
            limit_campaigns=limit_campaigns,
            max_workers=args.max_workers,
            include_details=args.include_details,
            keep_history=keep_history,
            write_db=write_db,
            db_path=db_path,
        )
        print_json(result)
    except OzonConfigError as exc:
        cli_error(exc)


if __name__ == '__main__':
    main()
