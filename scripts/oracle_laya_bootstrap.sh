#!/usr/bin/env bash
# Run on an Oracle Always Free Ubuntu 24.04 Ampere A1 VM after cloning ArchRivet.
# Usage: sudo bash scripts/oracle_laya_bootstrap.sh <public-hostname>
set -euo pipefail

hostname="${1:-}"
if [[ ! "$hostname" =~ ^[A-Za-z0-9.-]+$ || "$hostname" != *.* ]]; then
  echo 'Provide a public DNS hostname, for example 203.0.113.8.sslip.io' >&2
  exit 2
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo 'Run as root with sudo on the Oracle VM.' >&2
  exit 2
fi
if [[ "$(uname -m)" != 'aarch64' ]]; then
  echo 'This bootstrap targets the Always Free Ampere A1 (ARM64) VM.' >&2
  exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3.12 python3.12-venv python3-pip caddy openssl
if ! id archrivet >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/archrivet --create-home --shell /usr/sbin/nologin archrivet
fi
install -d -o archrivet -g archrivet -m 0750 /var/lib/archrivet /var/lib/archrivet/models
install -d -m 0755 /opt/archrivet
python3.12 -m venv /opt/archrivet/venv
/opt/archrivet/venv/bin/python -m pip install --upgrade pip
/opt/archrivet/venv/bin/python -m pip install 'torch==2.6.0' --index-url https://download.pytorch.org/whl/cpu
/opt/archrivet/venv/bin/python -m pip install "${repo}[model]"

model=/var/lib/archrivet/models/archrivet-322m
if [[ ! -f "$model/decision-contract.json" ]]; then
  if [[ -e "$model" ]]; then
    echo "Incomplete model directory exists at $model; inspect it before retrying." >&2
    exit 1
  fi
  runuser -u archrivet -- env ARCH_REVIEW_HOME=/var/lib/archrivet \
    /opt/archrivet/venv/bin/arch-review download-model \
    --variant archrivet-experimental --destination "$model"
fi
runuser -u archrivet -- env ARCH_REVIEW_HOME=/var/lib/archrivet \
  /opt/archrivet/venv/bin/arch-review configure \
  --checkpoint "$model" --backend laya --device cpu --context-tokens 2048 --port 8765

install -d -m 0750 -o root -g archrivet /etc/archrivet
if [[ ! -f /etc/archrivet/http.env ]]; then
  umask 027
  printf 'ARCH_REVIEW_HTTP_TOKEN=%s\n' "$(openssl rand -hex 32)" > /etc/archrivet/http.env
  chown root:archrivet /etc/archrivet/http.env
  chmod 0640 /etc/archrivet/http.env
fi

cat > /etc/systemd/system/archrivet-api.service <<'UNIT'
[Unit]
Description=ArchRivet local Laya review API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=archrivet
Group=archrivet
WorkingDirectory=/var/lib/archrivet
Environment=ARCH_REVIEW_HOME=/var/lib/archrivet
ExecStart=/opt/archrivet/venv/bin/arch-review serve
Restart=on-failure
RestartSec=5
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/archrivet-mcp.service <<'UNIT'
[Unit]
Description=ArchRivet Laya HTTP MCP
After=archrivet-api.service
Requires=archrivet-api.service

[Service]
Type=simple
User=archrivet
Group=archrivet
WorkingDirectory=/var/lib/archrivet
Environment=ARCH_REVIEW_HOME=/var/lib/archrivet
EnvironmentFile=/etc/archrivet/http.env
ExecStart=/opt/archrivet/venv/bin/arch-review mcp-http --port 8789
Restart=on-failure
RestartSec=10
TimeoutStartSec=600
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/caddy/Caddyfile <<CADDY
${hostname} {
    reverse_proxy 127.0.0.1:8789 {
        header_up Host 127.0.0.1:8789
    }
}
CADDY

systemctl daemon-reload
systemctl enable --now archrivet-api.service archrivet-mcp.service caddy.service
systemctl restart caddy.service
echo "Laya host configured. Wait for HTTPS, then check: https://${hostname}/mcp (401 without the gateway token)."
echo 'For the Cloudflare secret LAYA_ORIGIN_TOKEN, read /etc/archrivet/http.env on this VM. Keep it private.'
