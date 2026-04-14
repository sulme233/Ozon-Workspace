from __future__ import annotations

import unittest

from scripts.smoke_test_interfaces import build_parser, build_serve_command, extract_first_store_code


class SmokeInterfacesTests(unittest.TestCase):
    def test_build_serve_command_includes_optional_flags(self) -> None:
        args = build_parser().parse_args(
            [
                '--host',
                '0.0.0.0',
                '--port',
                '9000',
                '--days',
                '5',
                '--store',
                'ozon_a',
                '--limit-campaigns',
                '12',
                '--max-workers',
                '3',
                '--include-details',
                '--no-history',
                '--no-db',
                '--db-path',
                'C:/tmp/smoke.db',
            ]
        )

        cmd = build_serve_command(args)
        joined = ' '.join(cmd)

        self.assertIn('run_ozon_dashboard.py', joined)
        self.assertIn('--serve', cmd)
        self.assertIn('--host', cmd)
        self.assertIn('0.0.0.0', cmd)
        self.assertIn('--port', cmd)
        self.assertIn('9000', cmd)
        self.assertIn('--store', cmd)
        self.assertIn('ozon_a', cmd)
        self.assertIn('--limit-campaigns', cmd)
        self.assertIn('12', cmd)
        self.assertIn('--include-details', cmd)
        self.assertIn('--no-history', cmd)
        self.assertIn('--no-db', cmd)
        self.assertIn('--db-path', cmd)
        self.assertIn('C:/tmp/smoke.db', cmd)

    def test_extract_first_store_code_returns_first_non_empty(self) -> None:
        snapshot = {
            'payload': {
                'results': [
                    {'store_code': ''},
                    {'store_code': 'ozon_a'},
                    {'store_code': 'ozon_b'},
                ]
            }
        }
        self.assertEqual(extract_first_store_code(snapshot), 'ozon_a')

    def test_extract_first_store_code_handles_missing_payload(self) -> None:
        self.assertEqual(extract_first_store_code(None), '')
        self.assertEqual(extract_first_store_code({}), '')
        self.assertEqual(extract_first_store_code({'payload': {'results': []}}), '')


if __name__ == '__main__':
    unittest.main()
