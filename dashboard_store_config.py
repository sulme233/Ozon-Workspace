from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ozon_db import (
    DEFAULT_DB_PATH,
    create_store_config_version,
    get_store_config,
    list_store_configs,
    rollback_store_config_to_version,
    seed_store_configs,
    upsert_store_config,
)
from ozon_lib import (
    OzonConfigError,
    build_store_admin_view,
    load_config,
    save_config,
    upsert_store_in_config,
)


def get_store_by_code(config: Dict[str, Any], store_code: str) -> Dict[str, Any] | None:
    code = str(store_code or '').strip()
    for store in config.get('stores', []) or []:
        if str((store or {}).get('store_code', '')).strip() == code:
            return dict(store)
    return None


def list_store_admin_views(*, db_path: str) -> List[Dict[str, Any]]:
    stores = list_store_configs(db_path=db_path)
    return [build_store_admin_view(store) for store in stores]


def config_from_store_rows(stores: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {'stores': stores}


def sync_store_configs_from_json(*, db_path: str) -> int:
    config = load_config()
    return seed_store_configs(list(config.get('stores', []) or []), db_path=db_path)


def sync_store_configs_to_json(*, db_path: str) -> str:
    stores = list_store_configs(include_disabled=True, db_path=db_path)
    save_config(config_from_store_rows(stores))
    return str(Path('secrets') / 'ozon_accounts.json')


def update_store_config_and_persist(
    store_payload: Dict[str, Any],
    *,
    original_store_code: str = '',
    db_path: str = str(DEFAULT_DB_PATH),
    actor_username: str = '',
) -> Dict[str, Any]:
    json_config = load_config()
    next_config = upsert_store_in_config(json_config, store_payload, original_store_code=original_store_code)
    target_code = str(store_payload.get('store_code') or original_store_code or '').strip()
    stored = get_store_by_code(next_config, target_code)
    if stored is None:
        raise OzonConfigError(f'failed to persist store: {target_code}')
    previous = get_store_config(original_store_code or target_code, db_path=db_path)
    if previous:
        create_store_config_version(previous, action='before_update', actor_username=actor_username, db_path=db_path)
    upsert_store_config(stored, original_store_code=original_store_code, db_path=db_path)
    persisted = get_store_config(target_code, db_path=db_path)
    if persisted:
        create_store_config_version(persisted, action='after_update', actor_username=actor_username, db_path=db_path)
    sync_store_configs_to_json(db_path=db_path)
    return build_store_admin_view(stored)


def rollback_store_config_and_persist(
    store_code: str,
    version: int,
    *,
    db_path: str,
    actor_username: str = '',
) -> Dict[str, Any]:
    restored = rollback_store_config_to_version(
        store_code,
        version,
        actor_username=actor_username,
        db_path=db_path,
    )
    sync_store_configs_to_json(db_path=db_path)
    return build_store_admin_view(restored)
