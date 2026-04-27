# Deploy

## Runtime Model

- Backend entry: `run_ozon_dashboard.py --serve`
- Static dashboard files are served by the same process
- SQLite stores:
  - dashboard snapshots
  - admin users/sessions/audit logs
  - store configuration master data
- `secrets/ozon_accounts.json` is still kept in sync for pipeline compatibility

## Environment Variables

- `OZON_HOST`
- `OZON_PORT`
- `OZON_DB_PATH`
- `OZON_CONFIG_PATH`
- `OZON_ADMIN_USERNAME`
- `OZON_ADMIN_PASSWORD`
- `OZON_DASHBOARD_DAYS`
- `OZON_MAX_WORKERS`
- `OZON_LIMIT_CAMPAIGNS`
- `OZON_SESSION_TTL_HOURS`
- `OZON_SECURE_COOKIES`
- `OZON_LOGIN_RATE_WINDOW_SECONDS`
- `OZON_LOGIN_RATE_MAX_ATTEMPTS`

## Local Production-Style Start

```bash
pip install -r requirements.txt
set OZON_ADMIN_USERNAME=admin
set OZON_ADMIN_PASSWORD=your-password
python run_ozon_dashboard.py --serve --host 0.0.0.0 --port 8765
```

Open:

- `http://127.0.0.1:8765/index.html`

## Docker

Build:

```bash
docker build -t ozon-dashboard .
```

Run:

```bash
docker run -d --name ozon-dashboard \
  -p 8765:8765 \
  -e OZON_ADMIN_USERNAME=admin \
  -e OZON_ADMIN_PASSWORD=your-password \
  -e OZON_DB_PATH=/app/data/ozon_metrics.db \
  -e OZON_CONFIG_PATH=/app/secrets/ozon_accounts.json \
  -v %cd%/deploy/data:/app/data \
  -v %cd%/deploy/secrets:/app/secrets \
  ozon-dashboard
```

## Docker Compose

```bash
copy .env.example .env
# Edit .env and set OZON_ADMIN_USERNAME / OZON_ADMIN_PASSWORD before first start.
docker compose up -d --build
```

Before first start:

1. Create `deploy/secrets/`
2. Put `ozon_accounts.json` into `deploy/secrets/`
3. Copy `.env.example` to `.env` and set `OZON_ADMIN_USERNAME` / `OZON_ADMIN_PASSWORD`
4. Keep `.env`, `deploy/data/`, and `deploy/secrets/` out of git

## Smoke Validation

Before deployment or large runtime edits, run the local release gate:

```bash
python run_ozon.py release-check --backup
```

This runs the safe project status summary, local validation, and a runtime backup. Add `--api-smoke` when you also want to start the local dashboard service and probe local APIs without triggering a refresh:

```bash
python run_ozon.py release-check --backup --api-smoke
```

```bash
python run_ozon.py smoke --admin-username admin --admin-password your-password --skip-refresh
```

For a full validation:

```bash
python run_ozon.py smoke --admin-username admin --admin-password your-password
```

## Backup

Create a consistent runtime backup:

```bash
python run_ozon.py backup
```

The backup includes:

- SQLite database
- `ozon_accounts.json` if present
- manifest metadata
- zip archive

Use custom paths:

```bash
python run_ozon.py backup --db-path deploy/data/ozon_metrics.db --config-path deploy/secrets/ozon_accounts.json --backup-dir backups
```

Restore database only:

```bash
python run_ozon.py restore backups/ozon_backup_YYYYMMDD_HHMMSS.zip --db-path deploy/data/ozon_metrics.db --yes
```

Restore database and config:

```bash
python run_ozon.py restore backups/ozon_backup_YYYYMMDD_HHMMSS.zip --db-path deploy/data/ozon_metrics.db --config-path deploy/secrets/ozon_accounts.json --restore-config --yes
```

## Admin Management

List users:

```bash
python scripts/manage_admin.py list
```

Create user:

```bash
python scripts/manage_admin.py create alice
```

Reset password and revoke sessions:

```bash
python scripts/manage_admin.py set-password alice --revoke-sessions
```

Disable user:

```bash
python scripts/manage_admin.py disable alice
```

## Store Config Versioning

Every admin store edit records configuration versions in SQLite:

- `before_update`
- `after_update`
- `rollback:<version>`

The admin UI can load recent versions for the selected store and roll back to a prior version.

Notes:

- Version records are stored locally in SQLite and include the full config needed for rollback
- The UI only shows a summary and does not reveal full API keys
- After rollback, `ozon_accounts.json` is synced for pipeline compatibility

## Reverse Proxy

Use a reverse proxy for production HTTPS.

Example Nginx config:

- `deploy/nginx.conf.example`

When HTTPS is terminated by Nginx/Caddy, set:

```bash
OZON_SECURE_COOKIES=true
```

The backend reads `X-Forwarded-For` and `X-Real-IP` for login rate limiting.

## Service Manager

Linux systemd example:

- `deploy/ozon-dashboard.service.example`

Windows PowerShell start script:

- `deploy/start-windows.ps1`

## Security Hardening

- Change `OZON_ADMIN_PASSWORD` before first start
- Use `OZON_SECURE_COOKIES=true` behind HTTPS
- Keep `/app/data` and `/app/secrets` on persistent private volumes
- Do not expose the backend directly to the public Internet without HTTPS
- Keep `OZON_LOGIN_RATE_MAX_ATTEMPTS` low enough for public deployments
- Run backups before major edits or deployments

## Deployment Notes

- Use a persistent volume for `/app/data`
- Use a persistent volume for `/app/secrets`
- Do not bake real secrets into the image
- The server auto-bootstraps the first admin user from environment variables if no admin exists
- Store configuration is synced from JSON into SQLite on startup, and synced back to JSON after admin edits
