from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ozon_db import (
    authenticate_admin_user,
    bootstrap_admin_user,
    create_admin_session,
    create_store_config_version,
    create_admin_user,
    ensure_db,
    get_admin_session,
    get_latest_snapshot,
    list_store_config_versions,
    list_admin_users,
    list_store_configs,
    list_admin_audit_logs,
    list_snapshots,
    list_store_trends,
    revoke_admin_session,
    revoke_admin_sessions_for_user,
    rollback_store_config_to_version,
    save_snapshot,
    seed_store_configs,
    set_admin_active,
    set_admin_password,
    upsert_store_config,
    write_admin_audit_log,
)
from scripts.backup_runtime import create_backup
from scripts.restore_runtime import restore_backup


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
            'total_sales_amount_cny': sales * 7.2,
            'total_ad_expense_cny': 72.0,
            'total_ad_revenue_cny': 216.0,
            'total_low_stock_warehouses': 2,
            'overall_roas': 3.0,
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
        self.assertEqual(snapshots[0]['summary']['total_sales_amount_cny'], 720.0)
        self.assertEqual(snapshots[0]['summary']['total_low_stock_warehouses'], 2)

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
        self.assertEqual(latest['summary']['total_ad_expense_cny'], 72.0)

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

    def test_admin_user_session_and_audit_log_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            admin = bootstrap_admin_user('admin', 'secret-123', db_path=db_path)
            authed = authenticate_admin_user('admin', 'secret-123', db_path=db_path)
            self.assertEqual(admin['username'], 'admin')
            self.assertIsNotNone(authed)
            assert authed is not None

            session = create_admin_session(int(authed['id']), db_path=db_path, ttl_hours=4)
            current = get_admin_session(session['token'], db_path=db_path)
            self.assertIsNotNone(current)
            assert current is not None
            self.assertEqual(current['user']['username'], 'admin')

            log_id = write_admin_audit_log(
                'store.upsert',
                actor_username='admin',
                target_type='store',
                target_id='ozon_a',
                detail={'enabled': True},
                db_path=db_path,
            )
            logs = list_admin_audit_logs(limit=10, db_path=db_path)
            self.assertGreater(log_id, 0)
            self.assertEqual(logs[0]['action'], 'store.upsert')
            self.assertEqual(logs[0]['detail']['enabled'], True)

            revoked = revoke_admin_session(session['token'], db_path=db_path)
            after_revoke = get_admin_session(session['token'], db_path=db_path)
            self.assertTrue(revoked)
            self.assertIsNone(after_revoke)

    def test_admin_management_functions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            user = create_admin_user('alice', 'first-pass', db_path=db_path)
            self.assertEqual(user['username'], 'alice')
            self.assertIsNotNone(authenticate_admin_user('alice', 'first-pass', db_path=db_path))

            changed = set_admin_password('alice', 'second-pass', db_path=db_path)
            self.assertEqual(changed['username'], 'alice')
            self.assertIsNone(authenticate_admin_user('alice', 'first-pass', db_path=db_path))
            self.assertIsNotNone(authenticate_admin_user('alice', 'second-pass', db_path=db_path))

            session = create_admin_session(int(changed['id']), db_path=db_path)
            revoked_count = revoke_admin_sessions_for_user('alice', db_path=db_path)
            self.assertEqual(revoked_count, 1)
            self.assertIsNone(get_admin_session(session['token'], db_path=db_path))

            disabled = set_admin_active('alice', False, db_path=db_path)
            users = list_admin_users(db_path=db_path)

        self.assertFalse(disabled['is_active'])
        self.assertEqual(len(users), 1)

    def test_seed_and_upsert_store_configs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            seeded = seed_store_configs(
                [
                    {
                        'store_name': 'Alpha',
                        'store_code': 'ozon_a',
                        'enabled': True,
                        'timezone': 'Asia/Shanghai',
                        'currency': 'USD',
                        'notes': 'seeded',
                        'marketplace_id': 'RU',
                        'seller_api': {'client_id': 'seller-1', 'api_key': 'seller-key-1'},
                        'performance_api': {'client_id': 'perf-1', 'client_secret': 'perf-secret-1'},
                    }
                ],
                db_path=db_path,
            )
            self.assertEqual(seeded, 1)

            updated = upsert_store_config(
                {
                    'store_name': 'Alpha New',
                    'store_code': 'ozon_a',
                    'enabled': False,
                    'timezone': 'Asia/Shanghai',
                    'currency': 'CNY',
                    'notes': 'updated',
                    'marketplace_id': 'CN',
                    'seller_api': {'client_id': 'seller-2', 'api_key': 'seller-key-2'},
                    'performance_api': {'client_id': 'perf-2', 'client_secret': 'perf-secret-2'},
                },
                original_store_code='ozon_a',
                db_path=db_path,
            )
            stores = list_store_configs(db_path=db_path)

        self.assertEqual(updated['store_name'], 'Alpha New')
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0]['currency'], 'CNY')
        self.assertFalse(stores[0]['enabled'])
        self.assertEqual(stores[0]['seller_api']['api_key'], 'seller-key-2')

    def test_store_config_version_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'metrics.db'
            original = upsert_store_config(
                {
                    'store_name': 'Alpha',
                    'store_code': 'ozon_a',
                    'enabled': True,
                    'timezone': 'Asia/Shanghai',
                    'currency': 'USD',
                    'notes': 'original',
                    'marketplace_id': 'RU',
                    'seller_api': {'client_id': 'seller-1', 'api_key': 'seller-key-1'},
                    'performance_api': {'client_id': 'perf-1', 'client_secret': 'perf-secret-1'},
                },
                original_store_code='ozon_a',
                db_path=db_path,
            )
            version = create_store_config_version(original, action='seed', actor_username='tester', db_path=db_path)
            upsert_store_config(
                {
                    **original,
                    'store_name': 'Alpha Changed',
                    'currency': 'CNY',
                    'seller_api': {'client_id': 'seller-2', 'api_key': 'seller-key-2'},
                    'performance_api': {'client_id': 'perf-2', 'client_secret': 'perf-secret-2'},
                },
                original_store_code='ozon_a',
                db_path=db_path,
            )
            restored = rollback_store_config_to_version('ozon_a', int(version['version']), actor_username='tester', db_path=db_path)
            versions = list_store_config_versions('ozon_a', db_path=db_path)

        self.assertEqual(restored['store_name'], 'Alpha')
        self.assertEqual(restored['currency'], 'USD')
        self.assertGreaterEqual(len(versions), 2)
        self.assertEqual(versions[0]['action'], 'rollback:1')

    def test_backup_runtime_creates_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / 'metrics.db'
            config_path = root / 'ozon_accounts.json'
            backup_dir = root / 'backups'
            ensure_db(db_path)
            config_path.write_text('{"stores": []}', encoding='utf-8')

            result = create_backup(db_path=db_path, config_path=config_path, backup_dir=backup_dir, name='test')
            restored_db_path = root / 'restored.db'
            restore_result = restore_backup(
                archive_path=Path(result['archive']),
                db_path=restored_db_path,
                config_path=root / 'restored_accounts.json',
                restore_config=True,
                yes=True,
            )

        self.assertEqual(result['status'], 'ok')
        self.assertTrue(result['archive'].endswith('.zip'))
        self.assertEqual(restore_result['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
