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
python manage.py seed_pilot

echo ""
echo "Starting server at http://127.0.0.1:8000/"
echo "God of War: http://127.0.0.1:8000/game/god-of-war-ps4/"
echo ""
python manage.py runserver
