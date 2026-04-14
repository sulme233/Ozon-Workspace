from __future__ import annotations

import unittest
from unittest.mock import patch

from run_ozon_dashboard import build_summary, collect_dashboard_payload, refresh_dashboard, render_html


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
        'logistics': {'status': 'ok', 'summary': {'warehouse_count': 3, 'empty_stock_warehouses_count': 1, 'stock_reserved_ratio_pct': 15.5, 'stock_health_notes': ['Warehouse A has zero sampled stock']}},
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
    def test_build_summary_aggregates_metrics(self) -> None:
        summary = build_summary(
            [
                build_result(status='ok', health_score=80),
                build_result(store_name='Beta Store', store_code='BETA', status='error', sales_amount=300, ad_expense=0, ad_revenue=0, no_price_count=2, risky_sku_count=1, health_score=20),
            ]
        )

        self.assertEqual(summary['store_count'], 2)
        self.assertEqual(summary['ok_count'], 1)
        self.assertEqual(summary['error_count'], 1)
        self.assertEqual(summary['flagged_count'], 2)
        self.assertEqual(summary['total_no_price_items'], 9)
        self.assertEqual(summary['total_risky_skus'], 5)
        self.assertEqual(summary['avg_health_score'], 50.0)

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
        self.assertIn('./app.js', html)
        self.assertIn('stores-search', html)
        self.assertIn('attention-grid', html)
        self.assertIn('店铺经营态势', html)

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
        self.assertEqual(payload['results'], compact_results)

    def test_collect_dashboard_payload_keeps_details_when_requested(self) -> None:
        merged_results = [build_result()]
        with patch('run_ozon_dashboard.load_config', return_value={'stores': []}):
            with patch('run_ozon_dashboard.select_stores', return_value=[{'store_name': 'A', 'store_code': 'a'}]):
                with patch('run_ozon_dashboard.merge_store_results', return_value=merged_results):
                    with patch('run_ozon_dashboard.compact_store_results') as mock_compact:
                        payload = collect_dashboard_payload(days=1, include_details=True)

        mock_compact.assert_not_called()
        self.assertTrue(payload['include_details'])
        self.assertEqual(payload['results'], merged_results)

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


if __name__ == '__main__':
    unittest.main()
