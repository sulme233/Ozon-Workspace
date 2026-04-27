$ErrorActionPreference = "Stop"

if (-not $env:OZON_ADMIN_USERNAME) { $env:OZON_ADMIN_USERNAME = "admin" }
if (-not $env:OZON_ADMIN_PASSWORD) { throw "Set OZON_ADMIN_PASSWORD before starting" }
if (-not $env:OZON_HOST) { $env:OZON_HOST = "0.0.0.0" }
if (-not $env:OZON_PORT) { $env:OZON_PORT = "8765" }
if (-not $env:OZON_DB_PATH) { $env:OZON_DB_PATH = "$PSScriptRoot\data\ozon_metrics.db" }
if (-not $env:OZON_CONFIG_PATH) { $env:OZON_CONFIG_PATH = "$PSScriptRoot\secrets\ozon_accounts.json" }

python "$PSScriptRoot\..\run_ozon_dashboard.py" --serve --host $env:OZON_HOST --port $env:OZON_PORT
