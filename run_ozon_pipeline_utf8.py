from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    cmd = [sys.executable, 'run_ozon.py', 'daily', *sys.argv[1:]]
    completed = subprocess.run(cmd, env=env)
    return int(completed.returncode)


if __name__ == '__main__':
    raise SystemExit(main())
