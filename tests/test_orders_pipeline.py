from __future__ import annotations

import unittest
from unittest.mock import patch

from ozon_lib import OzonApiError
from run_ozon_orders_pipeline import analyze_store_orders


class OrdersPipelineTests(unittest.TestCase):
    def test_analyze_store_orders_returns_partial_when_unfulfilled_fails(self) -> None:
        with patch('run_ozon_orders_pipeline.fetch_fbs_postings', return_value=[]):
            with patch('run_ozon_orders_pipeline.fetch_fbs_unfulfilled_postings', side_effect=OzonApiError('bad window')):
                result = analyze_store_orders({'store_name': 'A', 'store_code': 'a', 'currency': 'USD'}, days=1)

        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['summary']['unfulfilled_count'], 0)
        self.assertIn('bad window', result['warnings'][0])

    def test_analyze_store_orders_counts_statuses(self) -> None:
        recent = [
            {'status': 'awaiting_packaging'},
            {'status': 'awaiting_deliver'},
            {'status': 'cancelled'},
        ]
        unfulfilled = [{'is_legal': True, 'shipment_date': '2026-04-14T10:00:00Z'}]
        with patch('run_ozon_orders_pipeline.fetch_fbs_postings', return_value=recent):
            with patch('run_ozon_orders_pipeline.fetch_fbs_unfulfilled_postings', return_value=unfulfilled):
                result = analyze_store_orders({'store_name': 'A', 'store_code': 'a', 'currency': 'USD'}, days=1)

        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['summary']['awaiting_packaging_count'], 1)
        self.assertEqual(result['summary']['awaiting_deliver_count'], 1)
        self.assertEqual(result['summary']['cancelled_count'], 1)
        self.assertEqual(result['summary']['legal_orders_count'], 1)
        self.assertEqual(result['summary']['shipment_attention_count'], 1)


if __name__ == '__main__':
    unittest.main()
