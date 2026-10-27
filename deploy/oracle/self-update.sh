#!/usr/bin/env bash
# Run by the garagedesk-update user timer every 5 minutes: when main has moved on, rebuild.
set -euo pipefail
BASE=${GARAGEDESK_BASE:-$HOME/garagedesk}
export DOCKER_HOST=${DOCKER_HOST:-unix:///run/user/$(id -u)/podman/podman.sock}
cd "$BASE/src"
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0
echo "main moved to $(git rev-parse --short origin/main), redeploying"
git pull -q --ff-only origin main
docker-compose --project-directory "$BASE/src" -f docker-compose.yml -f "$BASE/compose.local.yml" up -d --build
podman image prune -f >/dev/null || true
