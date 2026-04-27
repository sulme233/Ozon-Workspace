from __future__ import annotations

import datetime as dt
import unittest
from unittest.mock import patch

from ozon_lib import OzonApiError
from run_ozon_ads_pipeline import analyze_store_ads


def build_store() -> dict:
    return {
        'store_name': 'Store A',
        'store_code': 'ozon_a',
        'currency': 'USD',
        'performance_api': {'client_id': 'x', 'client_secret': 'y'},
    }


def build_csv() -> str:
    return (
        'ID;Название;Расход, ₽;Продажи, ₽;Заказы, шт.;Показы;Клики;В корзину;CTR;Средняя стоимость клика, ₽\n'
        '123;Campaign A;10;80;2;100;10;1;0,1;1\n'
    )


class AdsPipelineTests(unittest.TestCase):
    def test_future_interval_retries_previous_day_window(self) -> None:
        first_start = dt.date(2026, 4, 9)
        first_end = dt.date(2026, 4, 15)
        store = build_store()

        with patch('run_ozon_ads_pipeline.today_range', return_value=(first_start, first_end)):
            with patch('run_ozon_ads_pipeline.get_perf_token', return_value='token'):
                with patch(
                    'run_ozon_ads_pipeline.request_json',
                    return_value={'list': [{'id': 123, 'advObjectType': 'SKU'}]},
                ):
                    with patch(
                        'run_ozon_ads_pipeline.request_csv',
                        side_effect=[OzonApiError('future interval'), build_csv()],
                    ) as mock_csv:
                        with patch('run_ozon_ads_pipeline.fetch_campaign_objects', return_value={'123': [{'id': 'sku-1'}]}):
                            result = analyze_store_ads(store, days=7, limit_campaigns=None, object_workers=2)

        self.assertEqual(mock_csv.call_count, 2)
        retry_params = mock_csv.call_args_list[1].kwargs['params']
        retry_dict = {}
        for key, value in retry_params:
            if key not in retry_dict:
                retry_dict[key] = value
        self.assertEqual(retry_dict['dateFrom'], '2026-04-08')
        self.assertEqual(retry_dict['dateTo'], '2026-04-14')
        self.assertEqual(result['summary']['date_from'], '2026-04-08')
        self.assertEqual(result['summary']['date_to'], '2026-04-14')

    def test_non_future_error_is_raised(self) -> None:
        store = build_store()
        with patch('run_ozon_ads_pipeline.get_perf_token', return_value='token'):
            with patch(
                'run_ozon_ads_pipeline.request_json',
                return_value={'list': [{'id': 123, 'advObjectType': 'SKU'}]},
            ):
                with patch('run_ozon_ads_pipeline.request_csv', side_effect=OzonApiError('auth failed')):
                    with self.assertRaises(OzonApiError):
                        analyze_store_ads(store, days=7, limit_campaigns=None, object_workers=2)


if __name__ == '__main__':
    unittest.main()
