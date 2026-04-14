from __future__ import annotations

import unittest

from ozon_api_catalog import get_ozon_api_catalog


class OzonApiCatalogTests(unittest.TestCase):
    def test_catalog_returns_current_group(self) -> None:
        data = get_ozon_api_catalog(group='current')
        self.assertEqual(data['filter_group'], 'current')
        self.assertGreater(data['total_count'], 0)
        self.assertEqual(data['counts']['planned'], 0)

    def test_catalog_fallbacks_to_all(self) -> None:
        data = get_ozon_api_catalog(group='unknown')
        self.assertEqual(data['filter_group'], 'all')
        self.assertGreaterEqual(data['counts']['current'], 1)
        self.assertGreaterEqual(data['counts']['planned'], 1)


if __name__ == '__main__':
    unittest.main()
