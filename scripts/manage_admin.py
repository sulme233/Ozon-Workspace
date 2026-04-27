from __future__ import annotations

import argparse
import getpass
import pathlib

from ozon_db import (
    DEFAULT_DB_PATH,
    create_admin_user,
    list_admin_users,
    revoke_admin_sessions_for_user,
    set_admin_active,
    set_admin_password,
    write_admin_audit_log,
)
from ozon_lib import print_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Manage Ozon dashboard admin users')
    parser.add_argument('--db-path', type=pathlib.Path, default=DEFAULT_DB_PATH, help='SQLite database path')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('list', help='List admin users')

    create_parser = subparsers.add_parser('create', help='Create admin user')
    create_parser.add_argument('username')
    create_parser.add_argument('--password', default='', help='Password; prompts when omitted')

    password_parser = subparsers.add_parser('set-password', help='Set admin password')
    password_parser.add_argument('username')
    password_parser.add_argument('--password', default='', help='Password; prompts when omitted')
    password_parser.add_argument('--revoke-sessions', action='store_true', help='Revoke existing sessions after password change')

    disable_parser = subparsers.add_parser('disable', help='Disable admin user and revoke sessions')
    disable_parser.add_argument('username')

    enable_parser = subparsers.add_parser('enable', help='Enable admin user')
    enable_parser.add_argument('username')

    revoke_parser = subparsers.add_parser('revoke-sessions', help='Revoke admin user sessions')
    revoke_parser.add_argument('username')

    return parser


def read_password(raw: str) -> str:
    if raw:
        return raw
    first = getpass.getpass('Password: ')
    second = getpass.getpass('Confirm password: ')
    if first != second:
        raise SystemExit('password confirmation does not match')
    return first


def main() -> None:
    args = build_parser().parse_args()
    db_path = args.db_path

    if args.command == 'list':
        print_json({'status': 'ok', 'users': list_admin_users(db_path=db_path)})
        return

    if args.command == 'create':
        user = create_admin_user(args.username, read_password(args.password), db_path=db_path)
        write_admin_audit_log('admin.create', actor_username='cli', target_type='admin_user', target_id=user['username'], db_path=db_path)
        print_json({'status': 'ok', 'user': user})
        return

    if args.command == 'set-password':
        user = set_admin_password(args.username, read_password(args.password), db_path=db_path)
        revoked = revoke_admin_sessions_for_user(args.username, db_path=db_path) if args.revoke_sessions else 0
        write_admin_audit_log(
            'admin.set_password',
            actor_username='cli',
            target_type='admin_user',
            target_id=user['username'],
            detail={'revoked_sessions': revoked},
            db_path=db_path,
        )
        print_json({'status': 'ok', 'user': user, 'revoked_sessions': revoked})
        return

    if args.command == 'disable':
        user = set_admin_active(args.username, False, db_path=db_path)
        write_admin_audit_log('admin.disable', actor_username='cli', target_type='admin_user', target_id=user['username'], db_path=db_path)
        print_json({'status': 'ok', 'user': user})
        return

    if args.command == 'enable':
        user = set_admin_active(args.username, True, db_path=db_path)
        write_admin_audit_log('admin.enable', actor_username='cli', target_type='admin_user', target_id=user['username'], db_path=db_path)
        print_json({'status': 'ok', 'user': user})
        return

    if args.command == 'revoke-sessions':
        revoked = revoke_admin_sessions_for_user(args.username, db_path=db_path)
        write_admin_audit_log(
            'admin.revoke_sessions',
            actor_username='cli',
            target_type='admin_user',
            target_id=args.username,
            detail={'revoked_sessions': revoked},
            db_path=db_path,
        )
        print_json({'status': 'ok', 'revoked_sessions': revoked})
        return

    raise SystemExit(f'unknown command: {args.command}')


if __name__ == '__main__':
    main()
