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

pip install -q -r requirements.txt

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
