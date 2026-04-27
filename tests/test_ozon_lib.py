from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ozon_lib import (
    OzonConfigError,
    build_store_admin_view,
    fetch_finance_transactions,
    fetch_fbs_postings,
    fetch_fbs_unfulfilled_postings,
    fetch_product_prices,
    fetch_warehouses,
    inspect_config,
    load_config,
    require_positive_int,
    save_config,
    select_stores,
    store_matches_filter,
    upsert_store_in_config,
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

    def test_fetch_fbs_postings_collects_offset_pages(self) -> None:
        offsets = []

        def fake_request_json(*args, **kwargs):
            body = kwargs.get('json_body')
            offsets.append(body['offset'])
            if body['offset'] == 0:
                return {'result': {'postings': [{'posting_number': 'A'}], 'has_next': True}}
            return {'result': {'postings': [{'posting_number': 'B'}], 'has_next': False}}

        with patch('ozon_lib.seller_headers', return_value={}):
            with patch('ozon_lib.request_json', side_effect=fake_request_json):
                postings = fetch_fbs_postings({'store_name': 'Test'}, since='2026-04-01T00:00:00Z', to='2026-04-02T00:00:00Z', limit=1)

        self.assertEqual(offsets, [0, 1])
        self.assertEqual([item['posting_number'] for item in postings], ['A', 'B'])

    def test_fetch_fbs_unfulfilled_postings_collects_offset_pages(self) -> None:
        offsets = []

        def fake_request_json(*args, **kwargs):
            body = kwargs.get('json_body')
            offsets.append(body['offset'])
            if body['offset'] == 0:
                return {'result': {'postings': [{'posting_number': 'A'}], 'has_next': True}}
            return {'result': {'postings': [{'posting_number': 'B'}], 'has_next': False}}

        with patch('ozon_lib.seller_headers', return_value={}):
            with patch('ozon_lib.request_json', side_effect=fake_request_json):
                postings = fetch_fbs_unfulfilled_postings({'store_name': 'Test'}, limit=1)

        self.assertEqual(offsets, [0, 1])
        self.assertEqual([item['posting_number'] for item in postings], ['A', 'B'])

    def test_fetch_finance_transactions_collects_pages(self) -> None:
        pages = []

        def fake_request_json(*args, **kwargs):
            body = kwargs.get('json_body')
            pages.append(body['page'])
            if body['page'] == 1:
                return {'result': {'operations': [{'operation_id': '1'}], 'page_count': 2}}
            return {'result': {'operations': [{'operation_id': '2'}], 'page_count': 2}}

        with patch('ozon_lib.seller_headers', return_value={}):
            with patch('ozon_lib.request_json', side_effect=fake_request_json):
                operations = fetch_finance_transactions({'store_name': 'Test'}, days=1, page_size=1)

        self.assertEqual(pages, [1, 2])
        self.assertEqual([item['operation_id'] for item in operations], ['1', '2'])

    def test_fetch_product_prices_collects_cursor_pages(self) -> None:
        cursors = []

        def fake_request_json(*args, **kwargs):
            body = kwargs.get('json_body')
            cursors.append(body['cursor'])
            if body['cursor'] == '':
                return {'items': [{'offer_id': 'A'}], 'cursor': 'next'}
            return {'items': [{'offer_id': 'B'}], 'cursor': ''}

        with patch('ozon_lib.seller_headers', return_value={}):
            with patch('ozon_lib.request_json', side_effect=fake_request_json):
                items = fetch_product_prices({'store_name': 'Test'}, limit=1)

        self.assertEqual(cursors, ['', 'next'])
        self.assertEqual([item['offer_id'] for item in items], ['A', 'B'])

    def test_fetch_warehouses_collects_cursor_pages(self) -> None:
        cursors = []

        def fake_request_json(*args, **kwargs):
            body = kwargs.get('json_body')
            cursors.append(body['cursor'])
            if body['cursor'] == '':
                return {'warehouses': [{'warehouse_id': 1}], 'cursor': 'next'}
            return {'warehouses': [{'warehouse_id': 2}], 'cursor': ''}

        with patch('ozon_lib.seller_headers', return_value={}):
            with patch('ozon_lib.request_json', side_effect=fake_request_json):
                warehouses = fetch_warehouses({'store_name': 'Test'}, limit=1)

        self.assertEqual(cursors, ['', 'next'])
        self.assertEqual([item['warehouse_id'] for item in warehouses], [1, 2])

    def test_upsert_store_in_config_preserves_existing_secrets_when_blank(self) -> None:
        config = {
            'stores': [
                {
                    'store_name': 'Alpha',
                    'store_code': 'ozon_a',
                    'enabled': True,
                    'timezone': 'Asia/Shanghai',
                    'currency': 'USD',
                    'notes': '',
                    'seller_api': {'client_id': 'seller-1', 'api_key': 'seller-secret'},
                    'performance_api': {'client_id': 'perf-1', 'client_secret': 'perf-secret'},
                }
            ]
        }
        updated = upsert_store_in_config(
            config,
            {
                'store_name': 'Alpha 2',
                'store_code': 'ozon_a',
                'enabled': False,
                'currency': 'CNY',
                'seller_api': {'client_id': 'seller-2', 'api_key': ''},
                'performance_api': {'client_id': 'perf-2', 'client_secret': ''},
            },
            original_store_code='ozon_a',
        )
        store = updated['stores'][0]
        self.assertEqual(store['store_name'], 'Alpha 2')
        self.assertFalse(store['enabled'])
        self.assertEqual(store['currency'], 'CNY')
        self.assertEqual(store['seller_api']['client_id'], 'seller-2')
        self.assertEqual(store['seller_api']['api_key'], 'seller-secret')
        self.assertEqual(store['performance_api']['client_id'], 'perf-2')
        self.assertEqual(store['performance_api']['client_secret'], 'perf-secret')

    def test_save_and_load_config_roundtrip(self) -> None:
        config = {'stores': [build_store('Alpha', 'ALPHA')]}
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'ozon_accounts.json'
            save_config(config, config_path)
            loaded = load_config(config_path)
        self.assertEqual(loaded['stores'][0]['store_code'], 'ALPHA')

    def test_build_store_admin_view_masks_secrets(self) -> None:
        view = build_store_admin_view(
            {
                'store_name': 'Alpha',
                'store_code': 'ozon_a',
                'enabled': True,
                'seller_api': {'client_id': 'seller', 'api_key': 'abcd1234secret'},
                'performance_api': {'client_id': 'perf', 'client_secret': 'secret9876'},
            }
        )
        self.assertTrue(view['seller_api']['has_api_key'])
        self.assertTrue(view['performance_api']['has_client_secret'])
        self.assertTrue(view['seller_api']['api_key_masked'].endswith('cret'))
        self.assertTrue(view['performance_api']['client_secret_masked'].endswith('9876'))


if __name__ == '__main__':
    unittest.main()
