#!/usr/bin/env bash

set -euo pipefail

APP_DIR="${APP_DIR:-/srv/moments/app}"
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"

cd "$APP_DIR"

if [[ ! -d .git ]]; then
  echo "This directory is not a git repository: $APP_DIR" >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  echo "Missing virtual environment at $APP_DIR/.venv" >&2
  exit 1
fi

echo "Fetching latest code from $REMOTE/$BRANCH..."
git fetch "$REMOTE"
git pull --ff-only "$REMOTE" "$BRANCH"

echo "Installing or updating Python dependencies..."
source .venv/bin/activate
pip install -r requirements.txt
pip install gunicorn

echo "Restarting application service..."
systemctl restart moments
systemctl status moments --no-pager

echo "Health check..."
for attempt in 1 2 3 4 5; do
  if curl -I http://127.0.0.1:8000; then
    exit 0
  fi

  if [[ "$attempt" -lt 5 ]]; then
    echo "Health check not ready yet, retrying in 2 seconds..."
    sleep 2
  fi
done

echo "Health check failed after multiple attempts." >&2
exit 1
