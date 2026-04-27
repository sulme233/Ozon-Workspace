FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    OZON_HOST=0.0.0.0 \
    OZON_PORT=8765 \
    OZON_DB_PATH=/app/data/ozon_metrics.db \
    OZON_CONFIG_PATH=/app/secrets/ozon_accounts.json

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/data /app/secrets /app/dashboard/data

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import json, os, urllib.request; port=os.environ.get('OZON_PORT','8765'); data=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=3)); raise SystemExit(0 if data.get('status') == 'ok' else 1)"

CMD ["python", "run_ozon_dashboard.py", "--serve", "--host", "0.0.0.0", "--port", "8765"]
