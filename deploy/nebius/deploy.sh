#!/usr/bin/env bash
# Create (or reuse) a small Nebius AI Cloud VM and boot GarageDesk on it via cloud-init.
#
# Auth: either an already-configured `nebius` CLI profile (interactive login on a laptop),
# or a service account from the environment (CI / cloud thread):
#   NEBIUS_SA_ID, NEBIUS_PUBLIC_KEY_ID, NEBIUS_SA_PRIVATE_KEY (PEM text), NEBIUS_PROJECT_ID
# Required either way:
#   NEBIUS_PROJECT_ID   project-e00...   (nebius iam project list)
#   NEBIUS_API_KEY      Token Factory key baked into the VM's .env
# Optional:
#   NEBIUS_SUBNET_ID    (auto-picked: first subnet in the project)
#   SSH_PUBKEY_FILE     (~/.ssh/id_ed25519.pub) authorized for user ubuntu
#   TAVILY_API_KEY, VM_NAME (garagedesk), PLATFORM (cpu-d3), PRESET (2vcpu-8gb), DISK_GB (20)
set -euo pipefail
cd "$(dirname "$0")"

: "${NEBIUS_PROJECT_ID:?set NEBIUS_PROJECT_ID}"
: "${NEBIUS_API_KEY:?set NEBIUS_API_KEY}"
VM_NAME=${VM_NAME:-garagedesk}
PLATFORM=${PLATFORM:-cpu-d3}
PRESET=${PRESET:-2vcpu-8gb}
DISK_GB=${DISK_GB:-20}

command -v nebius >/dev/null || { echo "nebius CLI not found: https://docs.nebius.com/cli/install"; exit 1; }

# --- auth -------------------------------------------------------------------------------
if [[ -n "${NEBIUS_SA_ID:-}" ]]; then
  KEYFILE=$(mktemp); trap 'rm -f "$KEYFILE"' EXIT
  printf '%s\n' "$NEBIUS_SA_PRIVATE_KEY" > "$KEYFILE"
  nebius profile create --endpoint api.nebius.cloud --service-account-id "$NEBIUS_SA_ID" \
    --public-key-id "$NEBIUS_PUBLIC_KEY_ID" --private-key-file "$KEYFILE" \
    --profile garagedesk-deploy --parent-id "$NEBIUS_PROJECT_ID" >/dev/null
  nebius profile activate garagedesk-deploy >/dev/null 2>&1 || true
fi

# --- network ----------------------------------------------------------------------------
SUBNET_ID=${NEBIUS_SUBNET_ID:-$(nebius vpc subnet list --parent-id "$NEBIUS_PROJECT_ID" --format json \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["items"][0]["metadata"]["id"])')}
echo "subnet: $SUBNET_ID"

# --- cloud-init with secrets filled in --------------------------------------------------
USERDATA=$(mktemp); trap 'rm -f "$USERDATA" "${KEYFILE:-}"' EXIT
SSH_PUBKEY_FILE=${SSH_PUBKEY_FILE:-$HOME/.ssh/id_ed25519.pub}
[[ -f "$SSH_PUBKEY_FILE" ]] || { echo "no SSH public key at $SSH_PUBKEY_FILE (set SSH_PUBKEY_FILE)"; exit 1; }
sed -e "s|SSH_PUBLIC_KEY|$(cat "$SSH_PUBKEY_FILE")|" \
    -e "s|NEBIUS_API_KEY=REPLACE_ME|NEBIUS_API_KEY=${NEBIUS_API_KEY}|" \
    -e "s|TAVILY_API_KEY=$|TAVILY_API_KEY=${TAVILY_API_KEY:-}|" cloud-init.yaml > "$USERDATA"

# --- create or reuse the VM -------------------------------------------------------------
EXISTING=$(nebius compute instance list --parent-id "$NEBIUS_PROJECT_ID" --format json \
  | python3 -c 'import json,sys,os; d=json.load(sys.stdin); print(next((i["metadata"]["id"] for i in d.get("items",[]) if i["metadata"]["name"]==os.environ["VM_NAME"]),""))')
if [[ -n "$EXISTING" ]]; then
  echo "VM $VM_NAME already exists ($EXISTING); use redeploy.sh over SSH to update it."
  ID=$EXISTING
else
  ID=$(nebius compute instance create \
    --name "$VM_NAME" --parent-id "$NEBIUS_PROJECT_ID" \
    --resources-platform "$PLATFORM" --resources-preset "$PRESET" \
    --boot-disk-managed-disk-name "$VM_NAME-boot" --boot-disk-managed-disk-type network_ssd \
    --boot-disk-managed-disk-size-gibibytes "$DISK_GB" \
    --boot-disk-managed-disk-source-image-family-image-family ubuntu24.04-driverless \
    --boot-disk-attach-mode READ_WRITE \
    --network-interfaces "[{\"name\":\"eth0\",\"ip_address\":{},\"public_ip_address\":{\"static\":true},\"subnet_id\":\"$SUBNET_ID\"}]" \
    --cloud-init-user-data "$(cat "$USERDATA")" --format json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["metadata"]["id"])')
  echo "created VM $ID"
fi

# --- wait for the public IP --------------------------------------------------------------
for _ in $(seq 1 30); do
  IP=$(nebius compute instance get --id "$ID" --format json | python3 -c '
import json,sys
d=json.load(sys.stdin)
ifaces=(d.get("status") or {}).get("network_interfaces") or []
print((ifaces[0].get("public_ip_address") or {}).get("address","") if ifaces else "")' 2>/dev/null || true)
  [[ -n "$IP" ]] && break
  sleep 10
done
[[ -n "$IP" ]] || { echo "no public IP yet; check: nebius compute instance get --id $ID"; exit 1; }
IP=${IP%%/*}
echo "public IP: $IP"
echo "GarageDesk will be up at http://$IP/ in ~3 minutes (cloud-init builds the image)."
echo "Then: export PUBLIC_BASE_URL=http://$IP on the VM's /opt/garagedesk/src/.env and run deploy/nebius/redeploy.sh"
