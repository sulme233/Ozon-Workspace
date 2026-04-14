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


def render_html(payload: Dict[str, Any]) -> str:
    embedded = json.dumps(payload, ensure_ascii=False)
    template = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ozon 经营看板</title>
  <style>
    :root {
      --bg: #f4efe6;
      --ink: #182026;
      --muted: #60707d;
      --panel: rgba(255,255,255,0.78);
      --line: rgba(24,32,38,0.1);
      --accent: #125b50;
      --accent-2: #d96f32;
      --good: #2c8552;
      --warn: #b7791f;
      --bad: #c53030;
      --shadow: 0 18px 50px rgba(28, 33, 38, 0.12);
      --radius: 22px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(18,91,80,0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(217,111,50,0.14), transparent 24%),
        linear-gradient(180deg, #f6f1e7 0%, #efe6d8 100%);
    }
    .shell { max-width: 1480px; margin: 0 auto; padding: 28px; }
    .hero, .panel, .store {
      backdrop-filter: blur(8px);
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }
    .hero {
      border-radius: 32px;
      padding: 28px;
      margin-bottom: 22px;
      display: grid;
      gap: 18px;
    }
    .hero-top {
      display: flex;
      gap: 16px;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
    }
    .eyebrow {
      display: inline-block;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--accent);
      background: rgba(18,91,80,0.08);
      padding: 8px 12px;
      border-radius: 999px;
      margin-bottom: 10px;
    }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 34px; }
    .subtle { color: var(--muted); }
    .toolbar { display: flex; gap: 10px; flex-wrap: wrap; }
    button {
      border: 0;
      border-radius: 14px;
      padding: 12px 18px;
      cursor: pointer;
      font-weight: 700;
      color: white;
      background: linear-gradient(135deg, var(--accent), var(--accent-2));
      box-shadow: 0 12px 28px rgba(18,91,80,0.2);
    }
    button.ghost {
      color: var(--ink);
      background: rgba(255,255,255,0.6);
      border: 1px solid var(--line);
      box-shadow: none;
    }
    button[disabled] { opacity: 0.6; cursor: progress; }
    .hero-meta, .summary-grid, .store-grid {
      display: grid;
      gap: 12px;
    }
    .hero-meta { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .summary-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 22px; }
    .panel, .metric, .mini {
      border-radius: var(--radius);
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.7);
    }
    .meta-card, .metric, .mini { padding: 16px; }
    .label { color: var(--muted); font-size: 13px; margin-bottom: 8px; }
    .value { font-size: 28px; font-weight: 700; }
    .status-line {
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(18,91,80,0.08);
      color: var(--ink);
    }
    .stores { display: grid; gap: 18px; }
    .store {
      border-radius: 28px;
      padding: 22px;
    }
    .store-top {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .store-title { font-size: 22px; font-weight: 700; }
    .store-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 14px; }
    .badges, .chips { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge, .chip {
      border-radius: 999px;
      padding: 6px 10px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.8);
      font-size: 12px;
    }
    .badge.ok { color: var(--good); }
    .badge.partial { color: var(--warn); }
    .badge.error { color: var(--bad); }
    .section { margin-top: 14px; }
    .section h3 { margin-bottom: 8px; font-size: 14px; color: var(--muted); }
    ul { margin: 0; padding-left: 18px; }
    li { margin: 6px 0; }
    .table-wrap {
      overflow-x: auto;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.8);
    }
    table { width: 100%; border-collapse: collapse; min-width: 860px; }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      font-size: 13px;
      vertical-align: top;
    }
    th { color: var(--muted); background: rgba(18,91,80,0.05); }
    .empty {
      padding: 24px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.55);
    }
    .footer { margin-top: 20px; color: var(--muted); font-size: 12px; }
    @media (max-width: 1100px) {
      .hero-meta, .summary-grid, .store-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 720px) {
      .shell { padding: 16px; }
      .hero { padding: 20px; border-radius: 24px; }
      .hero-meta, .summary-grid, .store-grid { grid-template-columns: 1fr; }
      h1 { font-size: 28px; }
      .toolbar { width: 100%; }
      button { flex: 1; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-top">
        <div>
          <div class="eyebrow">Unified Operations Dashboard</div>
          <h1>Ozon 多店铺经营看板</h1>
          <p class="subtle" id="hero-desc"></p>
        </div>
        <div class="toolbar">
          <button id="refresh-btn" type="button">一键刷新数据</button>
          <button id="reload-btn" class="ghost" type="button">重新读取本地数据</button>
        </div>
      </div>
      <section class="hero-meta" id="hero-meta"></section>
      <div class="status-line" id="status-line">页面已加载当前快照。</div>
    </section>
    <section class="summary-grid" id="summary-grid"></section>
    <section class="stores" id="stores"></section>
    <div class="footer" id="footer-text"></div>
  </main>
  <script>
    const embeddedPayload = __EMBEDDED__;
    let payload = embeddedPayload;

    const fmt = (value) => new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(Number(value || 0));
    const escapeHtml = (value) => String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');

    function statusClass(status) {
      return status === 'ok' ? 'ok' : (status === 'partial' ? 'partial' : 'error');
    }

    function setStatus(message) {
      document.getElementById('status-line').textContent = message;
    }

    function renderDashboard(nextPayload) {
      payload = nextPayload || embeddedPayload;
      const summary = payload.summary || {};
      const results = payload.results || [];
      const refreshInfo = payload.refresh_info || {};

      document.getElementById('hero-desc').textContent =
        `统计周期 ${payload.days || 0} 天，店铺筛选：${payload.store_filter || '全部'}，生成时间：${payload.generated_at || '-'}`;
      document.getElementById('hero-meta').innerHTML = [
        ['最近刷新', refreshInfo.generated_at || payload.generated_at || '-'],
        ['店铺数', `${summary.store_count || 0}`],
        ['异常关注', `${summary.flagged_count || 0}`],
        ['平均健康分', `${summary.avg_health_score || 0}`],
      ].map(([label, value]) => `
        <div class="meta-card panel">
          <div class="label">${label}</div>
          <div class="value">${escapeHtml(value)}</div>
        </div>
      `).join('');

      document.getElementById('summary-grid').innerHTML = [
        ['总销售额', fmt(summary.total_sales_amount), `广告花费 ${fmt(summary.total_ad_expense_rub)}`],
        ['总广告收入', fmt(summary.total_ad_revenue_rub), `整体 ROAS ${fmt(summary.overall_roas)}`],
        ['待履约订单', fmt(summary.total_unfulfilled_orders), `低库存仓库 ${fmt(summary.total_low_stock_warehouses)}`],
        ['风险 SKU', fmt(summary.total_risky_skus), `无价格商品 ${fmt(summary.total_no_price_items)}`],
      ].map(([label, value, sub]) => `
        <div class="metric">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
          <div class="subtle">${sub}</div>
        </div>
      `).join('');

      document.getElementById('stores').innerHTML = results.length ? results.map((item) => {
        const overview = item.overview || {};
        const flags = item.flags || [];
        const insights = item.insights || [];
        const recommendations = item.recommendations || [];
        const skuRisks = ((item.sku_risk || {}).sku_risks_preview) || [];
        const errors = item.errors || [];
        return `
          <article class="store">
            <div class="store-top">
              <div>
                <div class="store-title">${escapeHtml(item.store_name || '-')}</div>
                <div class="subtle">${escapeHtml(item.store_code || '')}</div>
              </div>
              <div class="badges">
                <span class="badge ${statusClass(item.status || '')}">${escapeHtml(item.status || '-')}</span>
                <span class="badge">健康分 ${escapeHtml(item.health_score || 0)}</span>
              </div>
            </div>
            <section class="store-grid">
              <div class="mini"><div class="label">销售额</div><div class="value">${fmt(overview.sales_amount)}</div></div>
              <div class="mini"><div class="label">广告花费</div><div class="value">${fmt(overview.ad_expense_rub)}</div></div>
              <div class="mini"><div class="label">广告 ROAS</div><div class="value">${fmt(overview.ad_roas)}</div></div>
              <div class="mini"><div class="label">待履约</div><div class="value">${fmt(overview.unfulfilled_orders_count)}</div></div>
              <div class="mini"><div class="label">风险 SKU</div><div class="value">${fmt(overview.risky_sku_count)}</div></div>
            </section>
            <div class="section">
              <h3>风险标记</h3>
              <div class="chips">${(flags.length ? flags : ['当前未识别到明显风险']).map((x) => `<span class="chip">${escapeHtml(x)}</span>`).join('')}</div>
            </div>
            <div class="section">
              <h3>洞察</h3>
              <ul>${(insights.length ? insights : ['暂无洞察']).map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
            </div>
            <div class="section">
              <h3>建议</h3>
              <ul>${(recommendations.length ? recommendations : ['暂无建议']).map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
            </div>
            ${errors.length ? `
              <div class="section">
                <h3>模块错误</h3>
                <ul>${errors.map((x) => `<li>${escapeHtml((x.module || 'unknown') + ': ' + (x.error || ''))}</li>`).join('')}</ul>
              </div>
            ` : ''}
            <div class="section">
              <h3>风险 SKU 预览</h3>
              ${skuRisks.length ? `
                <div class="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>SKU</th>
                        <th>Offer</th>
                        <th>仓库</th>
                        <th>现货</th>
                        <th>预留</th>
                        <th>可用</th>
                        <th>价格</th>
                        <th>最低价</th>
                        <th>风险原因</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${skuRisks.map((row) => `
                        <tr>
                          <td>${escapeHtml(row.sku ?? '-')}</td>
                          <td>${escapeHtml(row.offer_id ?? '-')}</td>
                          <td>${escapeHtml(row.warehouse_name ?? '-')}</td>
                          <td>${fmt(row.present)}</td>
                          <td>${fmt(row.reserved)}</td>
                          <td>${fmt(row.free_stock)}</td>
                          <td>${row.price == null ? '-' : fmt(row.price)}</td>
                          <td>${row.min_price == null ? '-' : fmt(row.min_price)}</td>
                          <td>${escapeHtml((row.reasons || []).join(' / '))}</td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                </div>
              ` : '<div class="empty">当前没有风险 SKU 预览数据。</div>'}
            </div>
          </article>
        `;
      }).join('') : '<div class="empty">当前没有可展示的店铺数据。</div>';

      document.getElementById('footer-text').textContent =
        `最近刷新：${refreshInfo.generated_at || payload.generated_at || '-'}；数据文件：${refreshInfo.latest_json || '-'}`;
    }

    async function reloadLatestData() {
      try {
        setStatus('正在读取本地最新数据...');
        const response = await fetch('./data/latest.json', { cache: 'no-store' });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const nextPayload = await response.json();
        renderDashboard(nextPayload);
        setStatus(`本地数据已刷新，时间 ${nextPayload.generated_at || '-'}`);
      } catch (error) {
        setStatus(`读取本地数据失败: ${error.message}`);
      }
    }

    async function refreshData() {
      const btn = document.getElementById('refresh-btn');
      btn.disabled = true;
      try {
        setStatus('正在拉取最新数据并重建看板，这一步可能需要几十秒...');
        const response = await fetch('/api/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        const result = await response.json();
        if (!response.ok || result.status !== 'ok') {
          throw new Error(result.error || `HTTP ${response.status}`);
        }
        await reloadLatestData();
        setStatus(`刷新完成，时间 ${result.generated_at || '-'}`);
      } catch (error) {
        setStatus(`刷新失败: ${error.message}`);
      } finally {
        btn.disabled = false;
      }
    }

    document.getElementById('refresh-btn').addEventListener('click', refreshData);
    document.getElementById('reload-btn').addEventListener('click', reloadLatestData);

    if (location.protocol === 'file:') {
      setStatus('当前是静态文件模式，可查看数据；若需一键刷新，请使用 --serve 启动本地服务。');
    }

    renderDashboard(payload);
  </script>
</body>
</html>
"""
    return template.replace('__EMBEDDED__', embedded)


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
