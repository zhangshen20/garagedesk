#!/usr/bin/env bash
# Run by garagedesk-update.timer every few minutes: when main has moved on, redeploy.
# Merges to main go live on their own, with nobody's laptop in the loop.
set -euo pipefail
cd /opt/garagedesk/src
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] && exit 0
echo "main moved to $(git rev-parse --short origin/main), redeploying"
exec bash deploy/nebius/redeploy.sh
