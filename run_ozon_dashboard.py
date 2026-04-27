from __future__ import annotations

import argparse
import datetime as dt
import http.server
import json
import os
import socketserver
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

from dashboard_auth import (
    SESSION_COOKIE_NAME,
    bootstrap_admin_from_env_if_needed,
    clear_login_failures,
    cookie_max_age_seconds,
    env_bool,
    env_int,
    get_admin_bootstrap_status,
    get_client_ip,
    is_login_rate_limited,
    parse_cookies,
    record_login_failure,
)
from dashboard_jobs import (
    enqueue_refresh_job_with_overrides as _enqueue_refresh_job_with_overrides,
    get_latest_refresh_job,
    get_refresh_config_snapshot,
    get_refresh_job,
    refresh_config_view,
    refresh_job_view,
    resolve_refresh_config,
    update_refresh_defaults,
)
from dashboard_store_config import (
    list_store_admin_views,
    rollback_store_config_and_persist,
    sync_store_configs_from_json,
    sync_store_configs_to_json,
    update_store_config_and_persist,
)
from dashboard_probe import run_ozon_live_probe as _run_ozon_live_probe
from ozon_lib import (
    OzonConfigError,
    cli_error,
    fetch_fbs_postings,
    fetch_fbs_unfulfilled_postings,
    fetch_perf_campaigns,
    fetch_product_prices,
    fetch_warehouses,
    get_store_identity,
    list_store_identities,
    load_config,
    print_json,
    require_non_negative_int,
    require_positive_int,
    select_stores,
    today_range,
)
from ozon_api_catalog import get_ozon_api_catalog
from ozon_db import (
    DEFAULT_DB_PATH,
    authenticate_admin_user,
    bootstrap_admin_user,
    create_admin_session,
    ensure_db,
    get_admin_session,
    get_latest_snapshot,
    list_admin_audit_logs,
    list_snapshots,
    list_store_config_versions,
    list_store_trends,
    revoke_admin_session,
    save_snapshot,
    write_admin_audit_log,
)
from run_ozon_daily_pipeline import compact_store_results, merge_store_results


WORKSPACE = Path(__file__).resolve().parent
DASHBOARD_DIR = WORKSPACE / 'dashboard'
OUTPUT_FILE = DASHBOARD_DIR / 'index.html'
DATA_DIR = DASHBOARD_DIR / 'data'
LATEST_JSON_FILE = DATA_DIR / 'latest.json'
HISTORY_DIR = DATA_DIR / 'history'
MAX_JSON_BODY_BYTES = 1_000_000


def now_text() -> str:
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def enqueue_refresh_job(refresh_state: Dict[str, Any]) -> Dict[str, Any]:
    return enqueue_refresh_job_with_overrides(refresh_state, config_overrides=None)


def parse_refresh_config_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise OzonConfigError('refresh config payload must be an object')

    update: Dict[str, Any] = {}
    if 'days' in payload:
        update['days'] = require_positive_int(int(str(payload.get('days') or '').strip()), field='days')
    if 'store_filter' in payload:
        update['store_filter'] = str(payload.get('store_filter', '')).strip()
    if 'limit_campaigns' in payload:
        limit = require_non_negative_int(int(payload.get('limit_campaigns') or 0), field='limit_campaigns')
        update['limit_campaigns'] = (limit or None)
    if 'max_workers' in payload:
        update['max_workers'] = require_positive_int(int(str(payload.get('max_workers') or '').strip()), field='max_workers')
    if 'include_details' in payload:
        update['include_details'] = bool(payload.get('include_details'))
    if 'keep_history' in payload:
        update['keep_history'] = bool(payload.get('keep_history'))
    if 'write_db' in payload:
        update['write_db'] = bool(payload.get('write_db'))
    if 'db_path' in payload:
        path_text = str(payload.get('db_path') or '').strip()
        if not path_text:
            raise OzonConfigError('db_path cannot be empty')
        update['db_path'] = str(Path(path_text).expanduser())
    return update


def enqueue_refresh_job_with_overrides(
    refresh_state: Dict[str, Any],
    *,
    config_overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return _enqueue_refresh_job_with_overrides(
        refresh_state,
        config_overrides=config_overrides,
        refresh_dashboard_func=refresh_dashboard,
        now_text_func=now_text,
    )


def run_ozon_live_probe(
    *,
    store_filter: str = '',
    days: int = 7,
    request_timeout: int = 30,
) -> Dict[str, Any]:
    return _run_ozon_live_probe(
        store_filter=store_filter,
        days=days,
        request_timeout=request_timeout,
        now_text_func=now_text,
        load_config_func=load_config,
        select_stores_func=select_stores,
        today_range_func=today_range,
        fetch_perf_campaigns_func=fetch_perf_campaigns,
        fetch_product_prices_func=fetch_product_prices,
        fetch_warehouses_func=fetch_warehouses,
        fetch_fbs_postings_func=fetch_fbs_postings,
        fetch_fbs_unfulfilled_postings_func=fetch_fbs_unfulfilled_postings,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Generate or serve the Ozon dashboard')
    parser.add_argument('--days', type=int, default=int(os.environ.get('OZON_DASHBOARD_DAYS') or 7), help='Rolling day window')
    parser.add_argument('--store', type=str, default='', help='Filter by store name or store code')
    parser.add_argument('--limit-campaigns', type=int, default=int(os.environ.get('OZON_LIMIT_CAMPAIGNS') or 0), help='Limit campaigns per store, 0 means no limit')
    parser.add_argument('--max-workers', type=int, default=int(os.environ.get('OZON_MAX_WORKERS') or 4), help='Store-level parallel workers')
    parser.add_argument('--include-details', action='store_true', help='Include full module details in dashboard data')
    parser.add_argument('--no-history', action='store_true', help='Do not write dashboard history snapshot')
    parser.add_argument('--db-path', type=str, default=str(DEFAULT_DB_PATH), help='SQLite path for dashboard snapshots')
    parser.add_argument('--no-db', action='store_true', help='Do not persist snapshots into SQLite')
    parser.add_argument('--serve', action='store_true', help='Serve dashboard locally and enable in-page refresh')
    parser.add_argument('--host', type=str, default=str(os.environ.get('OZON_HOST') or '127.0.0.1'), help='Dashboard host')
    parser.add_argument('--port', type=int, default=int(os.environ.get('OZON_PORT') or 8765), help='Dashboard port')
    return parser


def get_exchange_rate_to_cny(currency: Any) -> float:
    code = str(currency or '').strip().upper()
    if code in {'CNY', 'RMB', 'CNH'}:
        return 1.0
    if code == 'USD':
        return 7.2
    return 1.0


def attach_currency_context(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw in results:
        item = dict(raw or {})
        currency = str(item.get('currency') or '').strip().upper() or 'CNY'
        item['currency'] = currency
        item['exchange_rate_to_cny'] = get_exchange_rate_to_cny(currency)
        items.append(item)
    return items


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    store_count = len(results)
    ok_count = len([item for item in results if item.get('status') == 'ok'])
    partial_count = len([item for item in results if item.get('status') == 'partial'])
    error_count = len([item for item in results if item.get('status') == 'error'])
    total_sales = 0.0
    total_ad_expense = 0.0
    total_ad_revenue = 0.0
    total_sales_cny = 0.0
    total_ad_expense_cny = 0.0
    total_ad_revenue_cny = 0.0
    for item in results:
        overview = item.get('overview') or {}
        rate = float(item.get('exchange_rate_to_cny') or get_exchange_rate_to_cny(item.get('currency')))
        sales = float(overview.get('sales_amount') or 0)
        ad_expense = float(overview.get('ad_expense_rub') or 0)
        ad_revenue = float(overview.get('ad_revenue_rub') or 0)
        total_sales += sales
        total_ad_expense += ad_expense
        total_ad_revenue += ad_revenue
        total_sales_cny += sales * rate
        total_ad_expense_cny += ad_expense * rate
        total_ad_revenue_cny += ad_revenue * rate
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
        'total_sales_amount_cny': round(total_sales_cny, 2),
        'total_ad_expense_rub': round(total_ad_expense, 2),
        'total_ad_expense_cny': round(total_ad_expense_cny, 2),
        'total_ad_revenue_rub': round(total_ad_revenue, 2),
        'total_ad_revenue_cny': round(total_ad_revenue_cny, 2),
        'total_unfulfilled_orders': total_unfulfilled,
        'total_low_stock_warehouses': total_low_stock,
        'total_no_price_items': total_no_price,
        'total_risky_skus': total_risky_sku,
        'overall_roas': round((total_ad_revenue_cny / total_ad_expense_cny), 2) if total_ad_expense_cny else 0,
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
    output_results = attach_currency_context(results if include_details else compact_store_results(results))
    generated_at = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return {
        'days': days,
        'store_filter': store_filter,
        'max_workers': max_workers,
        'include_details': bool(include_details),
        'generated_at': generated_at,
        'data_source': 'live',
        'refresh_info': {
            'generated_at': generated_at,
            'store_count': len(output_results),
            'latest_json': str(LATEST_JSON_FILE),
            'data_source': 'live',
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


def build_payload_view(
    payload: Dict[str, Any],
    *,
    store_code: str = '',
    snapshot_id: int | None = None,
    data_source: str = '',
    db_path: str = '',
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise OzonConfigError('dashboard payload must be an object')

    selected_store_code = str(store_code or '').strip()
    results = attach_currency_context(list(payload.get('results') or []))
    if selected_store_code:
        results = [
            item for item in results
            if str((item or {}).get('store_code') or '').strip() == selected_store_code
        ]

    refresh_info = dict(payload.get('refresh_info') or {})
    refresh_info['store_count'] = len(results)
    if snapshot_id is not None:
        refresh_info['snapshot_id'] = int(snapshot_id)
    if data_source:
        refresh_info['data_source'] = data_source
    if db_path:
        refresh_info['db_path'] = db_path

    return {
        **payload,
        'store_filter': selected_store_code or str(payload.get('store_filter') or ''),
        'selected_store_code': selected_store_code,
        'snapshot_id': int(snapshot_id) if snapshot_id is not None else payload.get('snapshot_id'),
        'data_source': data_source or str(payload.get('data_source') or ''),
        'db_path': db_path or str(payload.get('db_path') or ''),
        'refresh_info': refresh_info,
        'summary': build_summary(results),
        'results': results,
    }


def get_latest_dashboard_payload(
    *,
    db_path: str,
    store_code: str = '',
) -> Dict[str, Any] | None:
    snapshot = get_latest_snapshot(include_payload=True, db_path=db_path)
    if not isinstance(snapshot, dict):
        return None
    payload = snapshot.get('payload')
    if not isinstance(payload, dict):
        return None
    return build_payload_view(
        payload,
        store_code=store_code,
        snapshot_id=int(snapshot.get('id') or 0),
        data_source='sqlite',
        db_path=db_path,
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
          <button id="reload-btn" class="btn secondary" type="button">从数据库重载快照</button>
        </div>
      </div>
      <section class="hero-stats" id="hero-stats"></section>
      <div class="status-line" id="status-line">页面优先读取 SQLite 最新快照。</div>
    </section>

    <section class="toolbar-card" id="control-panel">
      <div class="toolbar-grid">
        <label class="field">
          <span class="field-label">统计天数</span>
          <input id="cfg-days" class="input" type="number" min="1" step="1" value="7">
        </label>
        <label class="field">
          <span class="field-label">店铺下拉选择</span>
          <select id="cfg-store-select" class="select">
            <option value="">全部店铺</option>
          </select>
        </label>
        <label class="field">
          <span class="field-label">店铺筛选（手动输入）</span>
          <input id="cfg-store-filter" class="input" type="text" placeholder="可输入店铺代号或店铺名称">
        </label>
        <label class="field">
          <span class="field-label">广告活动限制</span>
          <input id="cfg-limit-campaigns" class="input" type="number" min="0" step="1" value="0">
        </label>
        <label class="field">
          <span class="field-label">并发店铺数</span>
          <input id="cfg-max-workers" class="input" type="number" min="1" step="1" value="4">
        </label>
      </div>
      <div class="toolbar-grid">
        <label class="field"><span class="field-label">包含明细</span><input id="cfg-include-details" type="checkbox"></label>
        <label class="field"><span class="field-label">写入历史</span><input id="cfg-keep-history" type="checkbox" checked></label>
        <label class="field"><span class="field-label">自动写入数据库</span><input id="cfg-write-db" type="checkbox" checked disabled></label>
        <label class="field">
          <span class="field-label">数据库路径</span>
          <input id="cfg-db-path" class="input" type="text" placeholder="dashboard/data/ozon_metrics.db">
        </label>
      </div>
      <div class="toolbar">
        <button id="save-config-btn" class="btn secondary" type="button">保存页面配置</button>
        <button id="probe-btn" class="btn secondary" type="button">执行 Ozon 实时探测</button>
      </div>
      <div class="filter-row">
        <div class="filter-note" id="probe-output">探测结果将显示在这里。</div>
      </div>
    </section>

    <section class="toolbar-card admin-toggle-card" id="admin-workspace-toggle-card">
      <div class="section-head admin-toggle-head">
        <div>
          <h2>后台管理</h2>
          <p>登录、店铺配置和审计默认折叠，避免占用经营看板首屏。</p>
        </div>
        <button id="admin-workspace-toggle" class="btn secondary" type="button">展开后台管理</button>
      </div>
    </section>

    <section class="toolbar-card admin-panel is-collapsed" id="auth-panel">
      <div class="section-head">
        <div>
          <h2>后台鉴权</h2>
          <p>管理端操作需要登录后才能使用。首次启动时可以初始化管理员账号。</p>
        </div>
      </div>
      <div id="auth-panel-body"></div>
    </section>

    <section class="toolbar-card admin-panel is-collapsed" id="admin-store-panel">
      <div class="section-head">
        <div>
          <h2>店铺管理后台</h2>
          <p>统一管理店铺基础信息、Seller API Key 和 Performance Client Secret。</p>
        </div>
      </div>
      <div id="admin-store-body" class="empty">登录后可管理店铺。</div>
    </section>

    <section class="toolbar-card admin-panel is-collapsed" id="admin-audit-panel">
      <div class="section-head">
        <div>
          <h2>操作审计</h2>
          <p>记录管理员登录、配置保存、刷新和店铺配置变更。</p>
        </div>
      </div>
      <div id="admin-audit-body" class="empty">登录后可查看最近操作记录。</div>
    </section>

    <section class="overview-grid" id="overview-grid"></section>
    <section class="board-grid" id="attention-grid"></section>
    <section class="board-grid" id="data-grid"></section>

    <section class="toolbar-card">
      <div class="toolbar-grid">
        <label class="field">
          <span class="field-label">店铺切换</span>
          <select id="stores-select" class="select">
            <option value="">请选择店铺</option>
          </select>
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
          <span class="field-label">状态筛选</span>
          <div class="filter-group" id="status-filter-group"></div>
        </div>
      </div>
      <div class="view-actions">
        <div>
          <div class="field-label">卡片视图</div>
          <div class="filter-note">按当前筛选范围批量控制店铺详情展开状态。</div>
        </div>
        <div class="toolbar compact-actions">
          <button id="export-actions-csv-btn" class="btn secondary" type="button">导出动作 CSV</button>
          <button id="export-actions-json-btn" class="btn secondary" type="button">导出动作 JSON</button>
          <button id="expand-all-btn" class="btn secondary" type="button">展开当前店铺</button>
          <button id="expand-risk-btn" class="btn secondary" type="button">只展开异常店铺</button>
          <button id="collapse-all-btn" class="btn secondary" type="button">全部收起</button>
        </div>
      </div>
      <div class="filter-row">
        <div class="filter-note" id="filter-note"></div>
        <div class="filter-note">统一使用下拉框切换店铺，金额统一按人民币展示；系统会识别人民币店铺与美金店铺并按汇率换算。</div>
      </div>
    </section>

    <div class="section-head">
      <div>
        <h2>店铺经营态势</h2>
        <p>销售、广告、订单、价格、物流、SKU 风险六大模块一页汇总，先看趋势，再看动作清单。</p>
      </div>
    </div>
    <section class="stores" id="stores"></section>
    <div class="footer" id="footer-text"></div>
  </main>

  <script id="embedded-payload" type="application/json">__EMBEDDED__</script>
  <script src="./dashboard_format.js"></script>
  <script src="./dashboard_api.js"></script>
  <script src="./dashboard_state.js"></script>
  <script src="./dashboard_render_admin.js"></script>
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
    resolved_db_path = ensure_db(db_path) if write_db else str(Path(db_path).expanduser())
    sync_store_configs_from_json(db_path=resolved_db_path)
    bootstrap_admin_from_env_if_needed(db_path=resolved_db_path)
    session_ttl_hours = max(env_int('OZON_SESSION_TTL_HOURS', 24), 1)
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
        'config_lock': threading.Lock(),
        'jobs_lock': threading.Lock(),
        'refresh_job_seq': 0,
        'refresh_jobs': {},
        'refresh_job_order': [],
        'latest_refresh_job_id': None,
        'max_refresh_jobs': 30,
        'probe_lock': threading.Lock(),
        'latest_probe_result': None,
        'session_ttl_hours': session_ttl_hours,
        'secure_cookies': env_bool('OZON_SECURE_COOKIES', False),
        'auth_lock': threading.Lock(),
        'login_failures': {},
        'login_rate_window_seconds': max(env_int('OZON_LOGIN_RATE_WINDOW_SECONDS', 300), 1),
        'login_rate_max_attempts': max(env_int('OZON_LOGIN_RATE_MAX_ATTEMPTS', 8), 1),
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

        def _send_json_with_headers(self, status: int, payload: Dict[str, Any], headers: List[tuple[str, str]] | None = None) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            for key, value in headers or []:
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _read_json_body(self) -> Dict[str, Any]:
            raw_length = str(self.headers.get('Content-Length') or '').strip()
            if not raw_length:
                return {}
            try:
                length = int(raw_length)
            except Exception as exc:
                raise OzonConfigError(f'invalid content length: {raw_length}') from exc
            if length <= 0:
                return {}
            if length > MAX_JSON_BODY_BYTES:
                raise OzonConfigError(f'JSON body is too large: {length} bytes')

            body = self.rfile.read(length)
            if not body:
                return {}
            try:
                payload = json.loads(body.decode('utf-8'))
            except Exception as exc:
                raise OzonConfigError('invalid JSON body') from exc
            if payload is None:
                return {}
            if not isinstance(payload, dict):
                raise OzonConfigError('JSON body must be an object')
            return payload

        def _session_cookie_value(self) -> str:
            cookies = parse_cookies(str(self.headers.get('Cookie') or ''))
            return str(cookies.get(SESSION_COOKIE_NAME) or '').strip()

        def _set_session_cookie_header(self, token: str) -> tuple[str, str]:
            max_age = cookie_max_age_seconds(int(refresh_state.get('session_ttl_hours') or 24))
            secure = '; Secure' if bool(refresh_state.get('secure_cookies')) else ''
            return (
                'Set-Cookie',
                f'{SESSION_COOKIE_NAME}={token}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax{secure}',
            )

        @staticmethod
        def _clear_session_cookie_header() -> tuple[str, str]:
            return (
                'Set-Cookie',
                f'{SESSION_COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax',
            )

        def _current_session(self, *, touch: bool = True) -> Dict[str, Any] | None:
            token = self._session_cookie_value()
            if not token:
                return None
            return get_admin_session(token, touch=touch, db_path=refresh_state['db_path'])

        def _require_auth(self) -> Dict[str, Any] | None:
            session = self._current_session(touch=True)
            if session is None:
                self._send_json(401, {'status': 'error', 'error': 'authentication required'})
                return None
            return session

        def _write_audit(self, action: str, *, actor: str = '', target_type: str = '', target_id: str = '', detail: Dict[str, Any] | None = None) -> None:
            write_admin_audit_log(
                action,
                actor_username=actor,
                target_type=target_type,
                target_id=target_id,
                detail=detail or {},
                db_path=refresh_state['db_path'],
            )

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
                    with refresh_state['jobs_lock']:
                        active_jobs = sum(
                            1
                            for job in refresh_state['refresh_jobs'].values()
                            if str((job or {}).get('status', '')) in {'queued', 'running'}
                        )
                    self._send_json(
                        200,
                        {
                            'status': 'ok',
                            'db_path': refresh_state['db_path'],
                            'write_db': bool(refresh_state['write_db']),
                            'active_refresh_jobs': active_jobs,
                            'latest_refresh_job_id': refresh_state.get('latest_refresh_job_id'),
                            'auth': get_admin_bootstrap_status(db_path=refresh_state['db_path']),
                        },
                    )
                    return

                if parsed.path == '/api/auth/status':
                    session = self._current_session(touch=False)
                    self._send_json(
                        200,
                        {
                            'status': 'ok',
                            'authenticated': session is not None,
                            'session': session,
                            'bootstrap': get_admin_bootstrap_status(db_path=refresh_state['db_path']),
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

                if parsed.path == '/api/dashboard/latest':
                    store_code = (query.get('store_code') or [''])[0].strip()
                    payload = get_latest_dashboard_payload(
                        db_path=refresh_state['db_path'],
                        store_code=store_code,
                    )
                    if payload is None:
                        self._send_json(404, {'status': 'error', 'error': 'no snapshot available in sqlite'})
                        return
                    self._send_json(200, {'status': 'ok', 'payload': payload})
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

                if parsed.path == '/api/stores':
                    include_disabled = self._query_bool(query, 'include_disabled', default=False)
                    stores = list_store_identities(include_disabled=include_disabled)
                    items = [
                        {
                            'store_name': str(item.get('store_name', '')).strip(),
                            'store_code': str(item.get('store_code', '')).strip(),
                            'currency': str(item.get('currency', '')).strip(),
                            'enabled': bool(item.get('enabled', True)),
                        }
                        for item in stores
                    ]
                    self._send_json(200, {'status': 'ok', 'stores': items})
                    return

                if parsed.path == '/api/admin/stores':
                    session = self._require_auth()
                    if session is None:
                        return
                    self._send_json(200, {'status': 'ok', 'stores': list_store_admin_views(db_path=refresh_state['db_path']), 'session': session})
                    return

                if parsed.path == '/api/admin/audit-logs':
                    session = self._require_auth()
                    if session is None:
                        return
                    limit = self._query_int(query, 'limit', default=50, minimum=1, maximum=500)
                    self._send_json(200, {'status': 'ok', 'logs': list_admin_audit_logs(limit=limit, db_path=refresh_state['db_path'])})
                    return

                if parsed.path == '/api/admin/stores/versions':
                    session = self._require_auth()
                    if session is None:
                        return
                    store_code = (query.get('store_code') or [''])[0].strip()
                    if not store_code:
                        self._send_json(400, {'status': 'error', 'error': 'store_code is required'})
                        return
                    limit = self._query_int(query, 'limit', default=20, minimum=1, maximum=200)
                    versions = list_store_config_versions(store_code, limit=limit, db_path=refresh_state['db_path'])
                    self._send_json(200, {'status': 'ok', 'store_code': store_code, 'versions': versions})
                    return

                if parsed.path == '/api/ozon-api/catalog':
                    group = (query.get('group') or ['all'])[0]
                    catalog = get_ozon_api_catalog(group=group)
                    self._send_json(200, {'status': 'ok', 'catalog': catalog})
                    return

                if parsed.path == '/api/ozon/probe/latest':
                    with refresh_state['probe_lock']:
                        probe = refresh_state.get('latest_probe_result')
                    self._send_json(200, {'status': 'ok', 'probe': probe})
                    return

                if parsed.path == '/api/config':
                    session = self._require_auth()
                    if session is None:
                        return
                    config = refresh_config_view(get_refresh_config_snapshot(refresh_state))
                    self._send_json(200, {'status': 'ok', 'config': config})
                    return

                if parsed.path == '/api/refresh/status':
                    job_id = (query.get('job_id') or [''])[0].strip()
                    if not job_id:
                        self._send_json(400, {'status': 'error', 'error': 'job_id is required'})
                        return
                    job = get_refresh_job(refresh_state, job_id)
                    if job is None:
                        self._send_json(404, {'status': 'error', 'error': f'job not found: {job_id}'})
                        return
                    self._send_json(200, {'status': 'ok', 'job': job})
                    return

                if parsed.path == '/api/refresh/latest':
                    job = get_latest_refresh_job(refresh_state)
                    self._send_json(200, {'status': 'ok', 'job': job})
                    return

                self._send_json(404, {'status': 'error', 'error': f'Unknown API path: {parsed.path}'})
            except Exception as exc:
                self._send_json(500, {'status': 'error', 'error': str(exc)})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            if parsed.path not in {
                '/api/refresh',
                '/api/config',
                '/api/ozon/probe',
                '/api/auth/bootstrap',
                '/api/auth/login',
                '/api/auth/logout',
                '/api/admin/stores',
                '/api/admin/stores/rollback',
            }:
                self._send_json(404, {'status': 'error', 'error': f'Unknown API path: {parsed.path}'})
                return

            try:
                body = self._read_json_body()
            except OzonConfigError as exc:
                self._send_json(400, {'status': 'error', 'error': str(exc)})
                return

            if parsed.path == '/api/auth/bootstrap':
                try:
                    username = str(body.get('username') or '').strip()
                    password = str(body.get('password') or '')
                    user = bootstrap_admin_user(username, password, db_path=refresh_state['db_path'])
                    self._write_audit('auth.bootstrap', actor=user['username'], target_type='admin_user', target_id=user['username'])
                    self._send_json(200, {'status': 'ok', 'user': user})
                except Exception as exc:
                    self._send_json(400, {'status': 'error', 'error': str(exc)})
                return

            if parsed.path == '/api/auth/login':
                username = str(body.get('username') or '').strip()
                password = str(body.get('password') or '')
                client_ip = get_client_ip(self.headers, self.client_address)
                rate_key = f'{client_ip}:{username.casefold()}'
                if is_login_rate_limited(refresh_state, rate_key):
                    self._send_json(429, {'status': 'error', 'error': 'too many login attempts'})
                    return
                user = authenticate_admin_user(username, password, db_path=refresh_state['db_path'])
                if user is None:
                    record_login_failure(refresh_state, rate_key)
                    self._send_json(401, {'status': 'error', 'error': 'invalid username or password'})
                    return
                clear_login_failures(refresh_state, rate_key)
                session_info = create_admin_session(
                    int(user['id']),
                    ip_address=client_ip,
                    user_agent=str(self.headers.get('User-Agent') or ''),
                    ttl_hours=int(refresh_state['session_ttl_hours']),
                    db_path=refresh_state['db_path'],
                )
                self._write_audit('auth.login', actor=user['username'], target_type='admin_user', target_id=user['username'])
                self._send_json_with_headers(
                    200,
                    {'status': 'ok', 'user': user, 'session': {'expires_at': session_info['expires_at']}},
                    headers=[self._set_session_cookie_header(session_info['token'])],
                )
                return

            if parsed.path == '/api/auth/logout':
                token = self._session_cookie_value()
                session = self._current_session(touch=False)
                if token:
                    revoke_admin_session(token, db_path=refresh_state['db_path'])
                if session is not None:
                    self._write_audit(
                        'auth.logout',
                        actor=str((session.get('user') or {}).get('username') or ''),
                        target_type='admin_user',
                        target_id=str((session.get('user') or {}).get('username') or ''),
                    )
                self._send_json_with_headers(200, {'status': 'ok'}, headers=[self._clear_session_cookie_header()])
                return

            if parsed.path == '/api/config':
                session = self._require_auth()
                if session is None:
                    return
                try:
                    updates = parse_refresh_config_update(body)
                    new_config = update_refresh_defaults(refresh_state, updates)
                    self._write_audit(
                        'config.update',
                        actor=str((session.get('user') or {}).get('username') or ''),
                        target_type='refresh_config',
                        target_id='default',
                        detail={'fields': sorted(list(updates.keys()))},
                    )
                    self._send_json(200, {'status': 'ok', 'config': refresh_config_view(new_config)})
                except Exception as exc:
                    self._send_json(400, {'status': 'error', 'error': str(exc)})
                return

            if parsed.path == '/api/admin/stores':
                session = self._require_auth()
                if session is None:
                    return
                try:
                    original_store_code = str(body.get('original_store_code') or '').strip()
                    store_payload = dict(body.get('store') or body)
                    view = update_store_config_and_persist(
                        store_payload,
                        original_store_code=original_store_code,
                        db_path=refresh_state['db_path'],
                        actor_username=str((session.get('user') or {}).get('username') or ''),
                    )
                    self._write_audit(
                        'store.upsert',
                        actor=str((session.get('user') or {}).get('username') or ''),
                        target_type='store',
                        target_id=str(view.get('store_code') or ''),
                        detail={
                            'original_store_code': original_store_code,
                            'store_name': view.get('store_name'),
                            'enabled': view.get('enabled'),
                        },
                    )
                    self._send_json(200, {'status': 'ok', 'store': view})
                except Exception as exc:
                    self._send_json(400, {'status': 'error', 'error': str(exc)})
                return

            if parsed.path == '/api/admin/stores/rollback':
                session = self._require_auth()
                if session is None:
                    return
                try:
                    store_code = str(body.get('store_code') or '').strip()
                    version = require_positive_int(int(body.get('version') or 0), field='version')
                    actor = str((session.get('user') or {}).get('username') or '')
                    view = rollback_store_config_and_persist(
                        store_code,
                        version,
                        db_path=refresh_state['db_path'],
                        actor_username=actor,
                    )
                    self._write_audit(
                        'store.rollback',
                        actor=actor,
                        target_type='store',
                        target_id=store_code,
                        detail={'version': version},
                    )
                    self._send_json(200, {'status': 'ok', 'store': view})
                except Exception as exc:
                    self._send_json(400, {'status': 'error', 'error': str(exc)})
                return

            if parsed.path == '/api/ozon/probe':
                session = self._require_auth()
                if session is None:
                    return
                try:
                    probe_store_filter = str(body.get('store_filter') or '').strip()
                    probe_days = require_positive_int(int(body.get('days') or refresh_state['days']), field='days')
                    probe_timeout = require_positive_int(
                        int(body.get('request_timeout') or 30),
                        field='request_timeout',
                    )
                    with refresh_state['probe_lock']:
                        probe = run_ozon_live_probe(
                            store_filter=probe_store_filter,
                            days=probe_days,
                            request_timeout=probe_timeout,
                        )
                        refresh_state['latest_probe_result'] = probe
                    self._send_json(200, {'status': 'ok', 'probe': probe})
                except Exception as exc:
                    self._send_json(400, {'status': 'error', 'error': str(exc)})
                return

            # /api/refresh
            session = self._require_auth()
            if session is None:
                return
            try:
                refresh_updates = parse_refresh_config_update(body)
            except Exception as exc:
                self._send_json(400, {'status': 'error', 'error': str(exc)})
                return

            save_defaults = self._query_bool(query, 'save', default=False) or bool(body.get('save_defaults'))
            if save_defaults and refresh_updates:
                try:
                    update_refresh_defaults(refresh_state, refresh_updates)
                except Exception as exc:
                    self._send_json(400, {'status': 'error', 'error': str(exc)})
                    return

            wait_refresh = self._query_bool(query, 'wait', default=False) or (
                ((query.get('mode') or [''])[0].strip().lower() == 'sync')
            )

            if wait_refresh:
                try:
                    config = resolve_refresh_config(refresh_state, config_overrides=refresh_updates)
                except Exception as exc:
                    self._send_json(400, {'status': 'error', 'error': str(exc)})
                    return
                with refresh_state['refresh_lock']:
                    try:
                        result = refresh_dashboard(
                            days=config['days'],
                            store_filter=config['store_filter'],
                            limit_campaigns=config['limit_campaigns'],
                            max_workers=config['max_workers'],
                            include_details=config['include_details'],
                            keep_history=config['keep_history'],
                            write_db=config['write_db'],
                            db_path=config['db_path'],
                        )
                        self._write_audit(
                            'refresh.sync',
                            actor=str((session.get('user') or {}).get('username') or ''),
                            target_type='refresh_job',
                            target_id='sync',
                            detail={'config': refresh_config_view(config)},
                        )
                        self._send_json(200, result)
                    except Exception as exc:
                        self._send_json(500, {'status': 'error', 'error': str(exc)})
                return

            try:
                job = enqueue_refresh_job_with_overrides(refresh_state, config_overrides=refresh_updates)
                self._write_audit(
                    'refresh.enqueue',
                    actor=str((session.get('user') or {}).get('username') or ''),
                    target_type='refresh_job',
                    target_id=str(job['id']),
                    detail={'config_overrides': refresh_updates},
                )
                self._send_json(202, {'status': 'accepted', 'job_id': job['id'], 'job': job, 'saved_defaults': bool(save_defaults)})
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
