from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from ozon_lib import OzonConfigError
from run_ozon_daily_pipeline import compact_store_result, merge_store_results


def store(name: str, code: str) -> dict:
    return {'store_name': name, 'store_code': code}


class DailyPipelineTests(unittest.TestCase):
    def test_merge_store_results_preserves_store_order(self) -> None:
        stores = [store('A', 'a'), store('B', 'b'), store('C', 'c')]

        def fake_merge(store_item: dict, days: int, limit_campaigns: int | None) -> dict:
            # Simulate out-of-order completion.
            if store_item['store_code'] == 'a':
                time.sleep(0.03)
            elif store_item['store_code'] == 'b':
                time.sleep(0.01)
            return {
                'store_name': store_item['store_name'],
                'store_code': store_item['store_code'],
                'status': 'ok',
                'overview': {},
                'flags': [],
                'health_score': 100,
                'errors': [],
            }

        with patch('run_ozon_daily_pipeline.merge_store_result', side_effect=fake_merge):
            results = merge_store_results(stores, days=1, limit_campaigns=None, max_workers=3)

        self.assertEqual([item['store_code'] for item in results], ['a', 'b', 'c'])

    def test_merge_store_results_wraps_unexpected_exceptions(self) -> None:
        stores = [store('A', 'a'), store('B', 'b')]

        def fake_merge(store_item: dict, days: int, limit_campaigns: int | None) -> dict:
            if store_item['store_code'] == 'b':
                raise RuntimeError('boom')
            return {
                'store_name': store_item['store_name'],
                'store_code': store_item['store_code'],
                'status': 'ok',
                'overview': {},
                'flags': [],
                'health_score': 100,
                'errors': [],
            }

        with patch('run_ozon_daily_pipeline.merge_store_result', side_effect=fake_merge):
            results = merge_store_results(stores, days=1, limit_campaigns=None, max_workers=2)

        self.assertEqual(results[0]['status'], 'ok')
        self.assertEqual(results[1]['status'], 'error')
        self.assertEqual(results[1]['errors'][0]['module'], 'daily')
        self.assertIn('boom', results[1]['errors'][0]['error'])

    def test_merge_store_results_rejects_non_positive_workers(self) -> None:
        with self.assertRaises(OzonConfigError):
            merge_store_results([store('A', 'a')], days=1, limit_campaigns=None, max_workers=0)

    def test_compact_store_result_trims_large_fields(self) -> None:
        source = {
            'store_name': 'A',
            'store_code': 'a',
            'status': 'ok',
            'overview': {},
            'flags': [],
            'health_score': 90,
            'errors': [],
            'ads': {'detail': [1, 2, 3], 'alerts': list(range(30)), 'summary': {}},
            'orders': {'postings_preview': list(range(40)), 'summary': {}},
            'pricing': {'risky_items_preview': list(range(40)), 'summary': {}},
            'sales': {'operations_preview': list(range(40)), 'summary': {}},
            'logistics': {'warehouses': list(range(40)), 'stock_items_preview': list(range(100)), 'summary': {}},
            'sku_risk': {'sku_risks': list(range(100)), 'sku_risks_preview': list(range(80)), 'summary': {}},
        }

        compact = compact_store_result(source)

        self.assertNotIn('detail', compact['ads'])
        self.assertEqual(len(compact['ads']['alerts']), 20)
        self.assertEqual(len(compact['orders']['postings_preview']), 20)
        self.assertEqual(len(compact['pricing']['risky_items_preview']), 30)
        self.assertEqual(len(compact['sales']['operations_preview']), 30)
        self.assertEqual(len(compact['logistics']['warehouses']), 30)
        self.assertEqual(len(compact['logistics']['stock_items_preview']), 50)
        self.assertNotIn('sku_risks', compact['sku_risk'])
        self.assertEqual(len(compact['sku_risk']['sku_risks_preview']), 50)


if __name__ == '__main__':
    unittest.main()
