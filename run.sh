#!/usr/bin/env bash
# One-command local start for Game Price Tracker
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# Avoid contacting package indexes on every start. A newly-created or partial
# environment still installs the complete pinned dependency set automatically.
if ! python -c 'import bs4, celery, django, dotenv, environ, lxml, psycopg2, redis, requests' 2>/dev/null; then
  echo "Installing dependencies..."
  python -m pip install -r requirements.txt
fi

python manage.py migrate --noinput

# Optional seed (ignore if command missing)
python manage.py seed_launch_prices 2>/dev/null || python manage.py seed_pilot 2>/dev/null || true

echo ""
echo "Server:  http://127.0.0.1:8000/"
echo "Guide:   http://127.0.0.1:8000/guide/"
echo "About:   http://127.0.0.1:8000/about/"
echo "Dev map: DEVELOPER.md"
echo ""
python manage.py runserver
