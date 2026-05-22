#!/usr/bin/env bash
set -euo pipefail

CMD="${1:-api}"

case "$CMD" in
  api)
    echo "[entrypoint] running alembic migrations"
    alembic upgrade head
    echo "[entrypoint] starting FastAPI"
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers
    ;;
  worker)
    echo "[entrypoint] starting Celery worker"
    exec celery -A app.celery_app worker --loglevel=INFO --queues=biteplate.default,sms.send
    ;;
  beat)
    echo "[entrypoint] starting Celery Beat"
    exec celery -A app.celery_app beat --loglevel=INFO
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  shell)
    exec python
    ;;
  *)
    echo "[entrypoint] running custom command: $*"
    exec "$@"
    ;;
esac
