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
from run_ozon_daily_pipeline import merge_store_result


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


def collect_dashboard_payload(days: int, store_filter: str = '', limit_campaigns: int | None = None) -> Dict[str, Any]:
    require_positive_int(days, field='days')
    config = load_config()
    selected = select_stores(config, store_filter)
    results = [merge_store_result(store, days=days, limit_campaigns=limit_campaigns) for store in selected]
    generated_at = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return {
        'days': days,
        'store_filter': store_filter,
        'generated_at': generated_at,
        'refresh_info': {
            'generated_at': generated_at,
            'store_count': len(results),
            'latest_json': str(LATEST_JSON_FILE),
        },
        'summary': build_summary(results),
        'results': results,
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


def refresh_dashboard(days: int, store_filter: str = '', limit_campaigns: int | None = None) -> Dict[str, Any]:
    payload = collect_dashboard_payload(days=days, store_filter=store_filter, limit_campaigns=limit_campaigns)
    files = write_dashboard_files(payload)
    return {
        'status': 'ok',
        'output': files['html'],
        'latest_json': files['latest_json'],
        'history_json': files['history_json'],
        'store_count': len(payload.get('results', [])),
        'generated_at': payload.get('generated_at'),
    }


def serve_dashboard(host: str, port: int, days: int, store_filter: str = '', limit_campaigns: int | None = None) -> None:
    refresh_state: Dict[str, Any] = {
        'days': days,
        'store_filter': store_filter,
        'limit_campaigns': limit_campaigns,
        'refresh_lock': threading.Lock(),
    }

    class DashboardHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != '/api/refresh':
                self.send_error(404, 'Not Found')
                return

            with refresh_state['refresh_lock']:
                try:
                    result = refresh_dashboard(
                        days=refresh_state['days'],
                        store_filter=refresh_state['store_filter'],
                        limit_campaigns=refresh_state['limit_campaigns'],
                    )
                    body = json.dumps(result, ensure_ascii=False).encode('utf-8')
                    self.send_response(200)
                except Exception as exc:
                    body = json.dumps({'status': 'error', 'error': str(exc)}, ensure_ascii=False).encode('utf-8')
                    self.send_response(500)

            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
        })
        httpd.serve_forever()


def main() -> None:
    try:
        args = build_parser().parse_args()
        require_positive_int(args.days, field='days')
        require_non_negative_int(args.limit_campaigns, field='limit_campaigns')
        store_filter = (args.store or '').strip()
        limit_campaigns = args.limit_campaigns or None
        if args.serve:
            serve_dashboard(args.host, args.port, days=args.days, store_filter=store_filter, limit_campaigns=limit_campaigns)
            return

        result = refresh_dashboard(days=args.days, store_filter=store_filter, limit_campaigns=limit_campaigns)
        print_json(result)
    except OzonConfigError as exc:
        cli_error(exc)


if __name__ == '__main__':
    main()
