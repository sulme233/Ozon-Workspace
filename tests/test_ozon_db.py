from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ozon_db import ensure_db, get_latest_snapshot, list_snapshots, list_store_trends, save_snapshot


def build_payload(*, generated_at: str, store_code: str, sales: float, health: int) -> dict:
    return {
        'days': 1,
        'store_filter': '',
        'max_workers': 2,
        'include_details': False,
        'generated_at': generated_at,
        'summary': {
            'store_count': 1,
            'ok_count': 1,
            'partial_count': 0,
            'error_count': 0,
            'flagged_count': 0,
            'total_sales_amount': sales,
            'total_ad_expense_rub': 10.0,
            'total_ad_revenue_rub': 30.0,
            'total_unfulfilled_orders': 0,
            'total_no_price_items': 0,
            'total_risky_skus': 0,
            'avg_health_score': float(health),
        },
        'results': [
            {
                'store_name': 'Store A',
                'store_code': store_code,
                'currency': 'USD',
                'status': 'ok',
                'health_score': health,
                'flags': [],
                'errors': [],
                'overview': {
                    'sales_amount': sales,
                    'ad_expense_rub': 10.0,
                    'ad_revenue_rub': 30.0,
                    'ad_roas': 3.0,
                    'unfulfilled_orders_count': 0,
                    'no_price_count': 0,
                    'risky_sku_count': 0,
                },
            }
        ],
    }


class OzonDbTests(unittest.TestCase):
    def test_save_and_list_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            ensure_db(db_path)
            snapshot_id = save_snapshot(
                build_payload(generated_at='2026-04-15 10:00:00', store_code='ozon_a', sales=100.0, health=80),
                db_path=db_path,
            )

            snapshots = list_snapshots(limit=10, db_path=db_path)

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshot_id, snapshots[0]['id'])
        self.assertEqual(snapshots[0]['summary']['store_count'], 1)
        self.assertEqual(snapshots[0]['summary']['total_sales_amount'], 100.0)

    def test_get_latest_snapshot_with_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            save_snapshot(
                build_payload(generated_at='2026-04-15 10:00:00', store_code='ozon_a', sales=100.0, health=80),
                db_path=db_path,
            )
            latest = get_latest_snapshot(include_payload=True, db_path=db_path)

        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest['generated_at'], '2026-04-15 10:00:00')
        self.assertIn('payload', latest)
        self.assertEqual(latest['payload']['results'][0]['store_code'], 'ozon_a')

    def test_list_store_trends_orders_by_generated_at_desc(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            save_snapshot(
                build_payload(generated_at='2026-04-14 10:00:00', store_code='ozon_a', sales=80.0, health=60),
                db_path=db_path,
            )
            save_snapshot(
                build_payload(generated_at='2026-04-15 10:00:00', store_code='ozon_a', sales=120.0, health=90),
                db_path=db_path,
            )
            points = list_store_trends('ozon_a', limit=10, db_path=db_path)

        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]['generated_at'], '2026-04-15 10:00:00')
        self.assertEqual(points[0]['sales_amount'], 120.0)
        self.assertEqual(points[1]['generated_at'], '2026-04-14 10:00:00')


if __name__ == '__main__':
    unittest.main()
