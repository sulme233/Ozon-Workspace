from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import sqlite3
import zipfile
from typing import Dict

from ozon_db import DEFAULT_DB_PATH, ensure_db
from ozon_lib import DEFAULT_CONFIG, print_json


WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = WORKSPACE / 'backups'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Backup Ozon dashboard runtime data')
    parser.add_argument('--db-path', type=pathlib.Path, default=DEFAULT_DB_PATH, help='SQLite database path')
    parser.add_argument('--config-path', type=pathlib.Path, default=DEFAULT_CONFIG, help='Ozon accounts config path')
    parser.add_argument('--backup-dir', type=pathlib.Path, default=DEFAULT_BACKUP_DIR, help='Backup output directory')
    parser.add_argument('--name', type=str, default='', help='Optional backup name prefix')
    return parser


def backup_sqlite(db_path: pathlib.Path, target_path: pathlib.Path) -> None:
    ensure_db(db_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(db_path))
    try:
        dest = sqlite3.connect(str(target_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()


def create_backup(*, db_path: pathlib.Path, config_path: pathlib.Path, backup_dir: pathlib.Path, name: str = '') -> Dict[str, str]:
    timestamp = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
    prefix = f'{name.strip()}_' if name.strip() else ''
    backup_root = backup_dir / f'{prefix}ozon_backup_{timestamp}'
    backup_root.mkdir(parents=True, exist_ok=True)

    db_backup = backup_root / 'ozon_metrics.db'
    config_backup = backup_root / 'ozon_accounts.json'
    manifest_path = backup_root / 'manifest.json'
    archive_path = backup_dir / f'{backup_root.name}.zip'

    backup_sqlite(pathlib.Path(db_path), db_backup)
    if pathlib.Path(config_path).exists():
        shutil.copy2(config_path, config_backup)

    manifest = {
        'created_at': dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'db_path': str(db_path),
        'config_path': str(config_path),
        'files': {
            'sqlite': str(db_backup),
            'config': str(config_backup) if config_backup.exists() else '',
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')

    with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for item in backup_root.iterdir():
            archive.write(item, arcname=item.name)

    return {
        'status': 'ok',
        'backup_dir': str(backup_root),
        'archive': str(archive_path),
        'manifest': str(manifest_path),
    }


def main() -> None:
    args = build_parser().parse_args()
    print_json(
        create_backup(
            db_path=args.db_path,
            config_path=args.config_path,
            backup_dir=args.backup_dir,
            name=args.name,
        )
    )


if __name__ == '__main__':
    main()
