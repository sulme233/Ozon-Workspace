from __future__ import annotations

from typing import Any, Dict, List


CATALOG: List[Dict[str, Any]] = [
    {
        'group': 'current',
        'domain': 'performance',
        'method': 'POST',
        'path': '/api/client/token',
        'description': 'Get performance access token',
        'source': 'run_ozon_ads_pipeline.py / ozon_lib.py',
    },
    {
        'group': 'current',
        'domain': 'performance',
        'method': 'GET',
        'path': '/api/client/campaign',
        'description': 'List ad campaigns',
        'source': 'run_ozon_ads_pipeline.py',
    },
    {
        'group': 'current',
        'domain': 'performance',
        'method': 'GET',
        'path': '/api/client/campaign/{campaignId}/objects',
        'description': 'List campaign objects/SKU mappings',
        'source': 'run_ozon_ads_pipeline.py',
    },
    {
        'group': 'current',
        'domain': 'performance',
        'method': 'GET',
        'path': '/api/client/statistics/campaign/product',
        'description': 'Campaign product statistics export',
        'source': 'run_ozon_ads_pipeline.py',
    },
    {
        'group': 'current',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v3/finance/transaction/list',
        'description': 'Finance transactions list',
        'source': 'run_ozon_sales_pipeline.py / ozon_lib.py',
    },
    {
        'group': 'current',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v3/posting/fbs/list',
        'description': 'FBS posting list by period',
        'source': 'run_ozon_orders_pipeline.py / ozon_lib.py',
    },
    {
        'group': 'current',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v3/posting/fbs/unfulfilled/list',
        'description': 'FBS unfulfilled posting list',
        'source': 'run_ozon_orders_pipeline.py / ozon_lib.py',
    },
    {
        'group': 'current',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v5/product/info/prices',
        'description': 'Product prices and buybox context',
        'source': 'run_ozon_pricing_pipeline.py / ozon_lib.py',
    },
    {
        'group': 'current',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v2/warehouse/list',
        'description': 'Warehouse list',
        'source': 'run_ozon_logistics_pipeline.py',
    },
    {
        'group': 'current',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v2/delivery-method/list',
        'description': 'Delivery methods by warehouse',
        'source': 'run_ozon_logistics_pipeline.py',
    },
    {
        'group': 'current',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v1/product/info/warehouse/stocks',
        'description': 'Warehouse stock sample',
        'source': 'run_ozon_logistics_pipeline.py',
    },
    {
        'group': 'planned',
        'domain': 'performance',
        'method': 'POST',
        'path': '/api/client/statistics/phrases',
        'description': 'Search query phrase analytics',
        'source': 'docs/API_FEATURE_OPPORTUNITIES.md',
    },
    {
        'group': 'planned',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v3/posting/fbs/get',
        'description': 'Order-level FBS details and fulfillment checks',
        'source': 'docs/API_FEATURE_OPPORTUNITIES.md',
    },
    {
        'group': 'planned',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v4/product/info/stocks',
        'description': 'Product stock detail for inventory linkage',
        'source': 'docs/API_FEATURE_OPPORTUNITIES.md',
    },
    {
        'group': 'planned',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v1/product/info/stocks-by-warehouse/fbs',
        'description': 'FBS stock by warehouse',
        'source': 'docs/API_FEATURE_OPPORTUNITIES.md',
    },
    {
        'group': 'planned',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v3/finance/transaction/totals',
        'description': 'Finance totals for period summary',
        'source': 'docs/API_FEATURE_OPPORTUNITIES.md',
    },
    {
        'group': 'planned',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v1/finance/cash-flow-statement/list',
        'description': 'Cash flow reporting',
        'source': 'docs/API_FEATURE_OPPORTUNITIES.md',
    },
    {
        'group': 'planned',
        'domain': 'seller',
        'method': 'POST',
        'path': '/v1/returns/list',
        'description': 'Returns analysis',
        'source': 'docs/API_FEATURE_OPPORTUNITIES.md',
    },
]


def get_ozon_api_catalog(group: str = 'all') -> Dict[str, Any]:
    normalized = str(group or 'all').strip().casefold()
    if normalized not in {'all', 'current', 'planned'}:
        normalized = 'all'

    endpoints = [
        item for item in CATALOG
        if normalized == 'all' or str(item.get('group', '')).casefold() == normalized
    ]
    by_group = {
        key: len([item for item in endpoints if item.get('group') == key])
        for key in ('current', 'planned')
    }
    return {
        'filter_group': normalized,
        'total_count': len(endpoints),
        'counts': by_group,
        'references': [
            'references/ozon_api/seller_api_zh.txt',
            'references/ozon_api/performance_api_zh.txt',
            'docs/API_FEATURE_OPPORTUNITIES.md',
        ],
        'endpoints': endpoints,
    }
