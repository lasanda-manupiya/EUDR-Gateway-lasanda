#!/usr/bin/env bash
# Start SustainZone EUDR Gateway locally (macOS / Linux / WSL).
set -euo pipefail
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Open Docker Desktop, wait for the engine to start, then run ./start.sh again."; exit 1
fi

echo "Stopping any previous copy of the gateway..."
docker compose down >/dev/null 2>&1 || true

port_busy() { (exec 3<>/dev/tcp/127.0.0.1/"$1") 2>/dev/null && exec 3>&- ; }
PORT=8000
while port_busy "$PORT"; do
  echo "Port $PORT is used by another program — trying $((PORT+1))."
  PORT=$((PORT+1))
done
export APP_PORT=$PORT

echo "Building and starting (first time takes a few minutes)..."
docker compose up -d --build

echo -n "Waiting for the app"
for i in $(seq 1 120); do
  if curl -fs "http://localhost:$PORT/healthz/" >/dev/null 2>&1; then echo " ready."; break; fi
  echo -n "."; sleep 2
  if [ "$i" = 120 ]; then echo; echo "App did not start. Showing logs:"; docker compose logs --tail 60 web; exit 1; fi
done

HAS_ADMIN=$(docker compose exec -T web python manage.py shell -c "from apps.accounts.models import User; print(User.objects.filter(role='sz_admin').exists())" | tail -1)
if [ "$HAS_ADMIN" != "True" ]; then
  echo; echo "Create your SustainZone Admin account:"
  read -rp "Email: " EMAIL
  read -rp "Full name: " NAME
  docker compose exec web python manage.py create_sz_admin --email "$EMAIL" --name "$NAME"
fi

URL="http://localhost:$PORT"
echo; echo "SustainZone EUDR Gateway is running at $URL"
echo "Stop it with ./stop.sh"
(command -v open >/dev/null && open "$URL") || (command -v xdg-open >/dev/null && xdg-open "$URL") || true
