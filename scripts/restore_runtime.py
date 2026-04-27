from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import tempfile
import zipfile
from typing import Dict

from ozon_db import DEFAULT_DB_PATH, ensure_db
from ozon_lib import DEFAULT_CONFIG, print_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Restore Ozon dashboard runtime backup')
    parser.add_argument('archive', type=pathlib.Path, help='Backup zip archive created by backup_runtime.py')
    parser.add_argument('--db-path', type=pathlib.Path, default=DEFAULT_DB_PATH, help='SQLite database restore target')
    parser.add_argument('--config-path', type=pathlib.Path, default=DEFAULT_CONFIG, help='Ozon accounts config restore target')
    parser.add_argument('--restore-config', action='store_true', help='Restore ozon_accounts.json from archive')
    parser.add_argument('--yes', action='store_true', help='Confirm overwrite without prompt')
    return parser


def confirm_overwrite(db_path: pathlib.Path, config_path: pathlib.Path, *, restore_config: bool, yes: bool) -> None:
    if yes:
        return
    targets = [str(db_path)]
    if restore_config:
        targets.append(str(config_path))
    answer = input(f'This will overwrite: {", ".join(targets)}. Continue? [y/N] ').strip().lower()
    if answer not in {'y', 'yes'}:
        raise SystemExit('restore cancelled')


def restore_backup(
    *,
    archive_path: pathlib.Path,
    db_path: pathlib.Path,
    config_path: pathlib.Path,
    restore_config: bool = False,
    yes: bool = False,
) -> Dict[str, str]:
    archive_path = pathlib.Path(archive_path)
    if not archive_path.exists():
        raise FileNotFoundError(f'backup archive not found: {archive_path}')
    confirm_overwrite(db_path, config_path, restore_config=restore_config, yes=yes)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = pathlib.Path(tmpdir)
        with zipfile.ZipFile(archive_path, 'r') as archive:
            archive.extractall(tmp_root)
        manifest_path = tmp_root / 'manifest.json'
        db_source = tmp_root / 'ozon_metrics.db'
        config_source = tmp_root / 'ozon_accounts.json'
        if not manifest_path.exists():
            raise ValueError('backup archive missing manifest.json')
        if not db_source.exists():
            raise ValueError('backup archive missing ozon_metrics.db')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_source, db_path)
        ensure_db(db_path)

        restored_config = ''
        if restore_config and config_source.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(config_source, config_path)
            restored_config = str(config_path)

    return {
        'status': 'ok',
        'archive': str(archive_path),
        'db_path': str(db_path),
        'config_path': restored_config,
        'backup_created_at': str(manifest.get('created_at') or ''),
    }


def main() -> None:
    args = build_parser().parse_args()
    print_json(
        restore_backup(
            archive_path=args.archive,
            db_path=args.db_path,
            config_path=args.config_path,
            restore_config=bool(args.restore_config),
            yes=bool(args.yes),
        )
    )


if __name__ == '__main__':
    main()
