from __future__ import annotations

import argparse
import json
import pathlib
import sys


WORKSPACE = pathlib.Path(__file__).resolve().parents[1]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from ozon_lib import DEFAULT_CONFIG, inspect_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Inspect Ozon config readiness')
    parser.add_argument('--config', type=pathlib.Path, default=DEFAULT_CONFIG, help='Path to ozon_accounts.json')
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = inspect_config(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
