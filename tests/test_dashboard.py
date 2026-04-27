from __future__ import annotations

import datetime as dt
import json
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from run_ozon_dashboard import (
    attach_currency_context,
    build_payload_view,
    build_summary,
    collect_dashboard_payload,
    enqueue_refresh_job,
    sync_store_configs_from_json,
    sync_store_configs_to_json,
    get_latest_refresh_job,
    get_refresh_job,
    parse_refresh_config_update,
    refresh_dashboard,
    refresh_config_view,
    refresh_job_view,
    resolve_refresh_config,
    render_html,
    run_ozon_live_probe,
    update_refresh_defaults,
    MAX_JSON_BODY_BYTES,
)
from ozon_db import list_store_trends, save_snapshot


def build_result(
    *,
    store_name: str = 'Alpha Store',
    store_code: str = 'ALPHA',
    status: str = 'partial',
    sales_amount: float = 1200.5,
    ad_expense: float = 320.4,
    ad_revenue: float = 980.0,
    no_price_count: int = 7,
    risky_sku_count: int = 4,
    health_score: int = 61,
    flags: list[str] | None = None,
) -> dict:
    return {
        'store_name': store_name,
        'store_code': store_code,
        'currency': 'CNY',
        'status': status,
        'health_score': health_score,
        'flags': flags or ['广告有花费但无订单'],
        'insights': ['广告花费 320.40，带来广告销售额 980.00，ROAS 3.06。'],
        'recommendations': ['暂停低转化广告组，优先排查主图、价格、评价和详情页。'],
        'errors': [{'module': 'orders', 'error': 'sample error'}] if status != 'ok' else [],
        'overview': {
            'sales_amount': sales_amount,
            'ad_expense_rub': ad_expense,
            'ad_revenue_rub': ad_revenue,
            'ad_roas': round((ad_revenue / ad_expense), 2) if ad_expense else 0,
            'unfulfilled_orders_count': 2,
            'low_stock_warehouses_count': 1,
            'no_price_count': no_price_count,
            'risky_sku_count': risky_sku_count,
            'awaiting_packaging_count': 1,
            'awaiting_deliver_count': 1,
            'refund_amount': 0,
            'service_amount': -20,
            'deep_discount_count': 0,
            'low_margin_candidates_count': 0,
            'warehouse_count': 3,
            'empty_stock_warehouses_count': 1,
            'stock_reserved_ratio_pct': 15.5,
            'out_of_stock_sku_count': 2,
            'low_free_stock_sku_count': 1,
        },
        'ads': {
            'status': 'ok',
            'summary': {
                'campaign_count': 3,
                'summary_text': '已有点击和花费，但暂无订单，建议持续观察并优化转化。',
            },
            'alerts': [
                {
                    'campaign_id': '123',
                    'campaign_name': '测试活动',
                    'expense_rub': 120,
                    'orders': 0,
                    'roas': 0,
                    'action': '观察优化',
                }
            ],
        },
        'sales': {'status': 'ok', 'summary': {'orders_count_estimated': 6}},
        'orders': {'status': 'partial', 'summary': {'shipment_attention_count': 1}},
        'pricing': {'status': 'ok', 'summary': {'no_price_count': no_price_count, 'deep_discount_count': 0}},
        'logistics': {
            'status': 'ok',
            'summary': {
                'warehouse_count': 3,
                'empty_stock_warehouses_count': 1,
                'stock_reserved_ratio_pct': 15.5,
                'stock_health_notes': ['Warehouse A has zero sampled stock'],
            },
        },
        'sku_risk': {
            'status': 'ok',
            'summary': {'risky_sku_count': risky_sku_count, 'out_of_stock_sku_count': 2},
            'sku_risks_preview': [
                {
                    'sku': 'SKU-1',
                    'offer_id': 'OFFER-1',
                    'warehouse_name': 'WH-A',
                    'free_stock': 0,
                    'price': None,
                    'reasons': ['无可用库存'],
                }
            ],
        },
    }


class DashboardTests(unittest.TestCase):
    def test_attach_currency_context_adds_exchange_rate(self) -> None:
        items = attach_currency_context([
            {'store_code': 'USD-A', 'currency': 'USD'},
            {'store_code': 'CNY-A', 'currency': 'CNY'},
            {'store_code': 'EMPTY-A', 'currency': ''},
        ])
        self.assertEqual(items[0]['exchange_rate_to_cny'], 7.2)
        self.assertEqual(items[1]['exchange_rate_to_cny'], 1.0)
        self.assertEqual(items[2]['currency'], 'CNY')
        self.assertEqual(items[2]['exchange_rate_to_cny'], 1.0)

    def test_build_summary_aggregates_metrics(self) -> None:
        summary = build_summary(
            attach_currency_context(
                [
                    build_result(status='ok', health_score=80),
                    build_result(store_name='Beta Store', store_code='BETA', status='error', sales_amount=300, ad_expense=0, ad_revenue=0, no_price_count=2, risky_sku_count=1, health_score=20),
                ]
            )
        )

        self.assertEqual(summary['store_count'], 2)
        self.assertEqual(summary['ok_count'], 1)
        self.assertEqual(summary['error_count'], 1)
        self.assertEqual(summary['flagged_count'], 2)
        self.assertEqual(summary['total_no_price_items'], 9)
        self.assertEqual(summary['total_risky_skus'], 5)
        self.assertEqual(summary['avg_health_score'], 50.0)
        self.assertEqual(summary['total_sales_amount_cny'], 1500.5)
        self.assertEqual(summary['total_ad_expense_cny'], 320.4)
        self.assertEqual(summary['total_ad_revenue_cny'], 980.0)

    def test_render_html_contains_new_dashboard_shell(self) -> None:
        payload = {
            'days': 7,
            'store_filter': '',
            'generated_at': '2026-04-15 10:00:00',
            'refresh_info': {'generated_at': '2026-04-15 10:00:00', 'store_count': 1, 'latest_json': 'dashboard/data/latest.json'},
            'summary': build_summary([build_result()]),
            'results': [build_result()],
        }

        html = render_html(payload)

        self.assertIn('Ozon 多店铺经营看板', html)
        self.assertIn('./app.css', html)
        self.assertIn('./dashboard_format.js', html)
        self.assertIn('./dashboard_api.js', html)
        self.assertIn('./dashboard_state.js', html)
        self.assertIn('./dashboard_render_admin.js', html)
        self.assertIn('./app.js', html)
        self.assertNotIn('stores-search', html)
        self.assertIn('stores-select', html)
        self.assertIn('cfg-store-select', html)
        self.assertIn('attention-grid', html)
        self.assertIn('店铺经营态势', html)
        self.assertIn('统一使用下拉框切换店铺', html)
        self.assertIn('人民币展示', html)
        self.assertIn('后台鉴权', html)
        self.assertIn('店铺管理后台', html)
        self.assertIn('admin-workspace-toggle', html)
        self.assertIn('展开后台管理', html)
        self.assertIn('admin-panel is-collapsed', html)
        self.assertIn('expand-all-btn', html)
        self.assertIn('expand-risk-btn', html)
        self.assertIn('collapse-all-btn', html)
        self.assertIn('export-actions-csv-btn', html)
        self.assertIn('export-actions-json-btn', html)
        self.assertIn('只展开异常店铺', html)

    def test_render_html_escapes_embedded_json(self) -> None:
        payload = {
            'days': 7,
            'store_filter': '',
            'generated_at': '2026-04-15 10:00:00',
            'refresh_info': {'generated_at': '2026-04-15 10:00:00', 'store_count': 1, 'latest_json': 'dashboard/data/latest.json'},
            'summary': build_summary([build_result(store_name='</script><script>alert(1)</script>')]),
            'results': [build_result(store_name='</script><script>alert(1)</script>')],
        }

        html = render_html(payload)

        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e', html)

    def test_collect_dashboard_payload_compacts_by_default(self) -> None:
        merged_results = [build_result()]
        compact_results = [build_result()]
        with patch('run_ozon_dashboard.load_config', return_value={'stores': []}):
            with patch('run_ozon_dashboard.select_stores', return_value=[{'store_name': 'A', 'store_code': 'a'}]):
                with patch('run_ozon_dashboard.merge_store_results', return_value=merged_results):
                    with patch('run_ozon_dashboard.compact_store_results', return_value=compact_results) as mock_compact:
                        payload = collect_dashboard_payload(days=1, include_details=False)

        mock_compact.assert_called_once_with(merged_results)
        self.assertFalse(payload['include_details'])
        self.assertEqual(payload['results'][0]['store_code'], compact_results[0]['store_code'])
        self.assertEqual(payload['results'][0]['exchange_rate_to_cny'], 1.0)
        self.assertEqual(payload['results'][0]['currency'], 'CNY')

    def test_collect_dashboard_payload_keeps_details_when_requested(self) -> None:
        merged_results = [build_result()]
        with patch('run_ozon_dashboard.load_config', return_value={'stores': []}):
            with patch('run_ozon_dashboard.select_stores', return_value=[{'store_name': 'A', 'store_code': 'a'}]):
                with patch('run_ozon_dashboard.merge_store_results', return_value=merged_results):
                    with patch('run_ozon_dashboard.compact_store_results') as mock_compact:
                        payload = collect_dashboard_payload(days=1, include_details=True)

        mock_compact.assert_not_called()
        self.assertTrue(payload['include_details'])
        self.assertEqual(payload['results'][0]['store_code'], merged_results[0]['store_code'])
        self.assertEqual(payload['results'][0]['exchange_rate_to_cny'], 1.0)
        self.assertEqual(payload['results'][0]['currency'], 'CNY')

    def test_build_payload_view_can_filter_single_store_and_mark_sqlite_source(self) -> None:
        payload = {
            'days': 2,
            'store_filter': '',
            'generated_at': '2026-04-15 10:00:00',
            'refresh_info': {'generated_at': '2026-04-15 10:00:00', 'store_count': 2},
            'summary': build_summary([build_result(), build_result(store_name='Beta', store_code='BETA', status='ok')]),
            'results': [build_result(), build_result(store_name='Beta', store_code='BETA', status='ok')],
        }

        view = build_payload_view(
            payload,
            store_code='BETA',
            snapshot_id=17,
            data_source='sqlite',
            db_path='dashboard/data/ozon_metrics.db',
        )

        self.assertEqual(view['snapshot_id'], 17)
        self.assertEqual(view['data_source'], 'sqlite')
        self.assertEqual(view['db_path'], 'dashboard/data/ozon_metrics.db')
        self.assertEqual(view['refresh_info']['snapshot_id'], 17)
        self.assertEqual(view['refresh_info']['store_count'], 1)
        self.assertEqual(len(view['results']), 1)
        self.assertEqual(view['results'][0]['store_code'], 'BETA')
        self.assertEqual(view['results'][0]['exchange_rate_to_cny'], 1.0)
        self.assertEqual(view['summary']['store_count'], 1)
        self.assertIn('total_sales_amount_cny', view['summary'])
        self.assertIn('total_ad_expense_cny', view['summary'])
        self.assertIn('total_ad_revenue_cny', view['summary'])

    def test_refresh_dashboard_can_skip_history_snapshot(self) -> None:
        payload = {
            'days': 1,
            'store_filter': '',
            'max_workers': 2,
            'include_details': False,
            'generated_at': '2026-04-15 10:00:00',
            'refresh_info': {'generated_at': '2026-04-15 10:00:00', 'store_count': 1, 'latest_json': 'dashboard/data/latest.json'},
            'summary': build_summary([build_result()]),
            'results': [build_result()],
        }
        files = {'html': 'dashboard/index.html', 'latest_json': 'dashboard/data/latest.json', 'history_json': ''}

        with patch('run_ozon_dashboard.collect_dashboard_payload', return_value=payload):
            with patch('run_ozon_dashboard.write_dashboard_files', return_value=files) as mock_write:
                result = refresh_dashboard(days=1, keep_history=False, write_db=False)

        mock_write.assert_called_once_with(payload, keep_history=False)
        self.assertEqual(result['history_json'], '')
        self.assertFalse(result['keep_history'])
        self.assertFalse(result['write_db'])

    def test_refresh_job_view_contains_result_preview(self) -> None:
        view = refresh_job_view(
            {
                'id': '3',
                'status': 'ok',
                'created_at': '2026-04-15 10:00:00',
                'started_at': '2026-04-15 10:00:01',
                'finished_at': '2026-04-15 10:00:05',
                'error': None,
                'result': {
                    'status': 'ok',
                    'store_count': 2,
                    'generated_at': '2026-04-15 10:00:05',
                    'snapshot_id': 88,
                    'latest_json': 'dashboard/data/latest.json',
                },
            }
        )
        self.assertEqual(view['id'], '3')
        self.assertEqual(view['status'], 'ok')
        self.assertEqual(view['result']['store_count'], 2)
        self.assertEqual(view['result']['snapshot_id'], 88)

    def test_enqueue_refresh_job_updates_job_status(self) -> None:
        refresh_state = {
            'days': 1,
            'store_filter': '',
            'limit_campaigns': None,
            'max_workers': 2,
            'include_details': False,
            'keep_history': False,
            'write_db': False,
            'db_path': 'dashboard/data/ozon_metrics.db',
            'refresh_lock': threading.Lock(),
            'config_lock': threading.Lock(),
            'jobs_lock': threading.Lock(),
            'refresh_job_seq': 0,
            'refresh_jobs': {},
            'refresh_job_order': [],
            'latest_refresh_job_id': None,
            'max_refresh_jobs': 10,
        }

        with patch(
            'run_ozon_dashboard.refresh_dashboard',
            return_value={
                'status': 'ok',
                'store_count': 1,
                'generated_at': '2026-04-15 10:00:00',
                'snapshot_id': 7,
            },
        ):
            created = enqueue_refresh_job(refresh_state)
            self.assertEqual(created['id'], '1')
            # Background thread may update status immediately to running/ok.
            self.assertIn(created['status'], {'queued', 'running', 'ok'})

            deadline = time.time() + 2
            current = get_refresh_job(refresh_state, '1')
            while current and current['status'] in {'queued', 'running'} and time.time() < deadline:
                time.sleep(0.02)
                current = get_refresh_job(refresh_state, '1')

        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current['status'], 'ok')
        self.assertEqual(current['result']['snapshot_id'], 7)
        latest = get_latest_refresh_job(refresh_state)
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest['id'], '1')

    def test_parse_refresh_config_update_and_defaults_roundtrip(self) -> None:
        update = parse_refresh_config_update(
            {
                'days': 3,
                'store_filter': 'ozon_a',
                'limit_campaigns': 0,
                'max_workers': 2,
                'include_details': True,
                'keep_history': False,
                'write_db': False,
            }
        )
        self.assertEqual(update['days'], 3)
        self.assertEqual(update['store_filter'], 'ozon_a')
        self.assertIsNone(update['limit_campaigns'])
        self.assertEqual(update['max_workers'], 2)
        self.assertTrue(update['include_details'])
        self.assertFalse(update['write_db'])

        refresh_state = {
            'days': 7,
            'store_filter': '',
            'limit_campaigns': None,
            'max_workers': 4,
            'include_details': False,
            'keep_history': True,
            'write_db': True,
            'db_path': 'dashboard/data/ozon_metrics.db',
            'config_lock': threading.Lock(),
        }
        new_config = update_refresh_defaults(refresh_state, update)
        view = refresh_config_view(new_config)
        self.assertEqual(view['days'], 3)
        self.assertEqual(view['store_filter'], 'ozon_a')
        self.assertEqual(view['limit_campaigns'], 0)
        self.assertEqual(view['max_workers'], 2)
        self.assertFalse(view['write_db'])

        resolved = resolve_refresh_config(refresh_state)
        self.assertEqual(resolved['days'], 3)
        self.assertEqual(resolved['store_filter'], 'ozon_a')
        self.assertIsNone(resolved['limit_campaigns'])

    def test_dashboard_json_body_size_limit_is_bounded(self) -> None:
        self.assertLessEqual(MAX_JSON_BODY_BYTES, 1_000_000)

    def test_run_ozon_live_probe_aggregates_checks(self) -> None:
        store = {
            'store_name': 'Probe Store',
            'store_code': 'ozon_a',
            'currency': 'USD',
        }
        with patch('run_ozon_dashboard.load_config', return_value={'stores': [store]}):
            with patch('run_ozon_dashboard.select_stores', return_value=[store]):
                with patch('run_ozon_dashboard.today_range', return_value=(dt.date(2026, 4, 14), dt.date(2026, 4, 15))):
                    with patch(
                        'run_ozon_dashboard.fetch_perf_campaigns',
                        return_value=[
                            {'id': 1, 'advObjectType': 'SKU'},
                            {'id': 2, 'advObjectType': 'SEARCH_PROMO'},
                        ],
                    ):
                        with patch(
                            'run_ozon_dashboard.fetch_product_prices',
                            return_value=[
                                {'price': {'price': '100', 'old_price': '120'}},
                                {'price': {'price': '0', 'old_price': '0'}},
                            ],
                        ):
                            with patch(
                                'run_ozon_dashboard.fetch_warehouses',
                                return_value=[
                                    {'warehouse_id': 1, 'status': 'ACTIVE'},
                                    {'warehouse_id': 2, 'status': 'DISABLED'},
                                ],
                            ):
                                with patch(
                                    'run_ozon_dashboard.fetch_fbs_postings',
                                    return_value=[{'status': 'awaiting_packaging'}, {'status': 'delivering'}],
                                ):
                                    with patch(
                                        'run_ozon_dashboard.fetch_fbs_unfulfilled_postings',
                                        return_value=[{'posting_number': 'X'}],
                                    ):
                                        probe = run_ozon_live_probe(store_filter='ozon_a', days=2, request_timeout=5)

        self.assertEqual(probe['status'], 'ok')
        self.assertEqual(probe['store_code'], 'ozon_a')
        self.assertEqual(probe['checks']['campaigns']['total_count'], 2)
        self.assertEqual(probe['checks']['campaigns']['sku_count'], 1)
        self.assertEqual(probe['checks']['prices']['sample_count'], 2)
        self.assertEqual(probe['checks']['prices']['no_price_count'], 1)
        self.assertEqual(probe['checks']['warehouses']['count'], 2)
        self.assertEqual(probe['checks']['warehouses']['active_count'], 1)
        self.assertEqual(probe['checks']['warehouses']['inactive_count'], 1)
        self.assertEqual(probe['checks']['postings']['sample_count'], 2)
        self.assertEqual(probe['checks']['unfulfilled']['count'], 1)
        self.assertEqual(probe['errors'], [])

    def test_sync_store_configs_json_roundtrip(self) -> None:
        import tempfile

        config = {
            'stores': [
                {
                    'store_name': 'Alpha',
                    'store_code': 'ozon_a',
                    'enabled': True,
                    'timezone': 'Asia/Shanghai',
                    'currency': 'USD',
                    'notes': 'seed',
                    'seller_api': {'client_id': 'seller-1', 'api_key': 'seller-key-1'},
                    'performance_api': {'client_id': 'perf-1', 'client_secret': 'perf-secret-1'},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'ozon_accounts.json'
            db_path = Path(tmpdir) / 'metrics.db'
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
            with patch('dashboard_store_config.load_config', return_value=config):
                seeded = sync_store_configs_from_json(db_path=str(db_path))
            self.assertEqual(seeded, 1)
            with patch('dashboard_store_config.save_config') as mock_save:
                saved_path = sync_store_configs_to_json(db_path=str(db_path))
            self.assertTrue(saved_path.endswith('secrets\\ozon_accounts.json') or saved_path.endswith('secrets/ozon_accounts.json'))
            mock_save.assert_called_once()

    def test_store_trends_include_operational_metrics(self) -> None:
        import tempfile

        payload = {
            'days': 7,
            'store_filter': '',
            'max_workers': 2,
            'include_details': False,
            'generated_at': '2026-04-26 12:00:00',
            'summary': build_summary([build_result()]),
            'results': [build_result()],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            snapshot_id = save_snapshot(payload, db_path=db_path)
            points = list_store_trends('ALPHA', limit=5, db_path=db_path)

        self.assertEqual(snapshot_id, 1)
        self.assertEqual(len(points), 1)
        point = points[0]
        self.assertEqual(point['store_code'], 'ALPHA')
        self.assertEqual(point['ad_expense_rub'], 320.4)
        self.assertEqual(point['ad_roas'], 3.06)
        self.assertEqual(point['unfulfilled_orders'], 2)
        self.assertEqual(point['no_price_count'], 7)
        self.assertEqual(point['risky_sku_count'], 4)

    def test_dashboard_trend_card_renders_operational_metrics(self) -> None:
        app_js = (Path(__file__).resolve().parents[1] / 'dashboard' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function renderTrendPoint', app_js)
        self.assertIn('return toRmb(item?.[key], item);', app_js)
        self.assertIn("广告 ${moneySummary(getTrendMoneyValue(item, 'ad_expense_rub'))}", app_js)
        self.assertIn('待履约 ${whole(item.unfulfilled_orders)}', app_js)
        self.assertIn('无价格 ${whole(item.no_price_count)}', app_js)
        self.assertIn('风险 SKU ${whole(item.risky_sku_count)}', app_js)


if __name__ == '__main__':
    unittest.main()
