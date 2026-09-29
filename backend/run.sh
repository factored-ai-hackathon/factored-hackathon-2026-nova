#!/bin/bash
# Lambda entrypoint: Lambda Web Adapter (layer) forwards each request to this server on $PORT.
cd "$LAMBDA_TASK_ROOT"
export PYTHONPATH="$LAMBDA_TASK_ROOT:${PYTHONPATH:-}"
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" --no-access-log
