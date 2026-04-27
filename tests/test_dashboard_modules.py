from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard_auth import (
    clear_login_failures,
    get_client_ip,
    is_login_rate_limited,
    parse_cookies,
    record_login_failure,
)
from dashboard_store_config import (
    get_store_by_code,
    rollback_store_config_and_persist,
    sync_store_configs_from_json,
    sync_store_configs_to_json,
    update_store_config_and_persist,
)
from ozon_db import create_store_config_version, upsert_store_config


class DashboardAuthModuleTests(unittest.TestCase):
    def test_parse_cookies_and_client_ip(self) -> None:
        self.assertEqual(parse_cookies('a=1; b=2')['b'], '2')
        headers = {'X-Forwarded-For': '1.2.3.4, 5.6.7.8'}
        self.assertEqual(get_client_ip(headers, ('127.0.0.1', 1)), '1.2.3.4')

    def test_login_rate_limit_helpers(self) -> None:
        state = {
            'auth_lock': threading.Lock(),
            'login_failures': {},
            'login_rate_window_seconds': 300,
            'login_rate_max_attempts': 2,
        }
        self.assertFalse(is_login_rate_limited(state, 'ip:user'))
        record_login_failure(state, 'ip:user')
        record_login_failure(state, 'ip:user')
        self.assertTrue(is_login_rate_limited(state, 'ip:user'))
        clear_login_failures(state, 'ip:user')
        self.assertFalse(is_login_rate_limited(state, 'ip:user'))


class DashboardStoreConfigModuleTests(unittest.TestCase):
    def test_store_config_sync_update_and_rollback(self) -> None:
        original_config = {
            'stores': [
                {
                    'store_name': 'Alpha',
                    'store_code': 'ozon_a',
                    'enabled': True,
                    'timezone': 'Asia/Shanghai',
                    'currency': 'USD',
                    'notes': '',
                    'seller_api': {'client_id': 'seller-1', 'api_key': 'key-1'},
                    'performance_api': {'client_id': 'perf-1', 'client_secret': 'secret-1'},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / 'metrics.db')
            with patch('dashboard_store_config.load_config', return_value=original_config):
                self.assertEqual(sync_store_configs_from_json(db_path=db_path), 1)

            first = upsert_store_config(original_config['stores'][0], original_store_code='ozon_a', db_path=db_path)
            version = create_store_config_version(first, action='seed', actor_username='tester', db_path=db_path)
            with patch('dashboard_store_config.load_config', return_value=original_config):
                with patch('dashboard_store_config.save_config') as mock_save:
                    view = update_store_config_and_persist(
                        {
                            'store_name': 'Alpha Changed',
                            'store_code': 'ozon_a',
                            'enabled': True,
                            'timezone': 'Asia/Shanghai',
                            'currency': 'CNY',
                            'seller_api': {'client_id': 'seller-2', 'api_key': 'key-2'},
                            'performance_api': {'client_id': 'perf-2', 'client_secret': 'secret-2'},
                        },
                        original_store_code='ozon_a',
                        db_path=db_path,
                        actor_username='tester',
                    )
                    self.assertEqual(view['currency'], 'CNY')
                    self.assertTrue(mock_save.called)

            with patch('dashboard_store_config.save_config'):
                restored = rollback_store_config_and_persist('ozon_a', int(version['version']), db_path=db_path, actor_username='tester')
            self.assertEqual(restored['currency'], 'USD')

    def test_get_store_by_code(self) -> None:
        config = {'stores': [{'store_code': 'ozon_a', 'store_name': 'Alpha'}]}
        self.assertEqual(get_store_by_code(config, 'ozon_a')['store_name'], 'Alpha')
        self.assertIsNone(get_store_by_code(config, 'missing'))


if __name__ == '__main__':
    unittest.main()
