#!/usr/bin/env bash
# From the laptop: copy the Token Factory / Tavily keys to the Oracle VM and run setup.sh there.
#   bash deploy/oracle/install-from-mac.sh
set -euo pipefail
VM=${ORACLE_VM:-opc@207.211.156.85}
KEY=${ORACLE_SSH_KEY:-$HOME/.ssh/id_rsa}
ENV_FILE=${ENV_FILE:-$HOME/Code/garagedesk/.env.deploy}
DOMAIN=${GARAGEDESK_DOMAIN-garagedesk.shenit.com.au}
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "$VM")
"${SSH[@]}" 'mkdir -p ~/garagedesk && umask 077 && cat > ~/garagedesk/garagedesk.env' < "$ENV_FILE"
"${SSH[@]}" "curl -fsSL https://raw.githubusercontent.com/zhangshen20/garagedesk/main/deploy/oracle/setup.sh -o ~/garagedesk/setup.sh && GARAGEDESK_DOMAIN=$DOMAIN bash ~/garagedesk/setup.sh"
