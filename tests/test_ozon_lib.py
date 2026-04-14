from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ozon_lib import (
    OzonConfigError,
    fetch_fbs_postings,
    inspect_config,
    require_positive_int,
    select_stores,
    store_matches_filter,
)


def build_store(
    name: str,
    code: str,
    *,
    enabled: bool = True,
    seller_ready: bool = True,
    perf_ready: bool = True,
) -> dict:
    return {
        'store_name': name,
        'store_code': code,
        'enabled': enabled,
        'seller_api': {
            'client_id': 'seller-client' if seller_ready else '',
            'api_key': 'seller-key' if seller_ready else '',
        },
        'performance_api': {
            'client_id': 'perf-client' if perf_ready else '',
            'client_secret': 'perf-secret' if perf_ready else '',
        },
    }


class OzonLibTests(unittest.TestCase):
    def test_store_matches_filter_supports_exact_and_partial_casefold(self) -> None:
        store = build_store('Moscow Alpha', 'ALPHA-01')
        self.assertTrue(store_matches_filter(store, 'moscow alpha'))
        self.assertTrue(store_matches_filter(store, 'alpha'))
        self.assertTrue(store_matches_filter(store, 'ALPHA-01'))
        self.assertFalse(store_matches_filter(store, 'beta'))

    def test_select_stores_skips_disabled_and_raises_for_unknown_filter(self) -> None:
        config = {
            'stores': [
                build_store('Alpha Store', 'ALPHA'),
                build_store('Beta Store', 'BETA', enabled=False),
            ]
        }
        selected = select_stores(config, 'alpha')
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['store_code'], 'ALPHA')

        with self.assertRaises(OzonConfigError):
            select_stores(config, 'beta')

    def test_require_positive_int_rejects_zero(self) -> None:
        with self.assertRaises(OzonConfigError):
            require_positive_int(0, field='days')
        self.assertEqual(require_positive_int(3, field='days'), 3)

    def test_inspect_config_reports_readiness_counts(self) -> None:
        config = {
            'stores': [
                build_store('Alpha Store', 'ALPHA'),
                build_store('Beta Store', 'BETA', perf_ready=False),
                build_store('Gamma Store', 'GAMMA', enabled=False, seller_ready=False),
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'ozon_accounts.json'
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
            summary = inspect_config(config_path)

        self.assertEqual(summary['store_count'], 3)
        self.assertEqual(summary['enabled_store_count'], 2)
        self.assertEqual(summary['seller_ready_count'], 2)
        self.assertEqual(summary['performance_ready_count'], 2)

    def test_fetch_fbs_postings_omits_empty_status_filter(self) -> None:
        captured = {}

        def fake_request_json(*args, **kwargs):
            captured['json_body'] = kwargs.get('json_body')
            return {'result': {'postings': []}}

        with patch('ozon_lib.seller_headers', return_value={}):
            with patch('ozon_lib.request_json', side_effect=fake_request_json):
                fetch_fbs_postings({'store_name': 'Test'}, since='2026-04-01T00:00:00Z', to='2026-04-02T00:00:00Z')

        self.assertNotIn('status', captured['json_body']['filter'])

    def test_fetch_fbs_postings_normalizes_status_filter(self) -> None:
        captured = {}

        def fake_request_json(*args, **kwargs):
            captured['json_body'] = kwargs.get('json_body')
            return {'result': {'postings': []}}

        with patch('ozon_lib.seller_headers', return_value={}):
            with patch('ozon_lib.request_json', side_effect=fake_request_json):
                fetch_fbs_postings(
                    {'store_name': 'Test'},
                    since='2026-04-01T00:00:00Z',
                    to='2026-04-02T00:00:00Z',
                    statuses=['', 'awaiting_packaging', '  '],
                )

        self.assertEqual(captured['json_body']['filter']['status'], ['awaiting_packaging'])


if __name__ == '__main__':
    unittest.main()
