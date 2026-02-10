#!/usr/bin/env bash
# ------------------------------------------------------------------
# Server setup for Lesgoski
#
# Works on any Ubuntu VPS (Hetzner, Oracle Cloud, AWS, etc.)
#
# Usage:
#   1. Provision a VPS, point a DuckDNS subdomain to its IP.
#   2. SSH in and run:  bash deploy/setup.sh YOUR_DOMAIN YOUR_EMAIL
# ------------------------------------------------------------------
set -euo pipefail

DOMAIN="${1:?Usage: $0 <domain> <email>}"
EMAIL="${2:?Usage: $0 <domain> <email>}"

echo "==> Installing Docker..."
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

echo "==> Opening firewall ports 80, 443 (if iptables is active)..."
if command -v iptables &>/dev/null && sudo iptables -L INPUT -n &>/dev/null 2>&1; then
    sudo iptables -I INPUT -p tcp --dport 80  -j ACCEPT
    sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
    sudo netfilter-persistent save || true
else
    echo "  No iptables firewall detected — skipping."
    echo "  If your provider has a cloud firewall (e.g. Hetzner), open ports 80+443 there."
fi

echo "==> Preparing .env file..."
if [ ! -f .env ]; then
    cp .env.example .env
    # Set the WEBAPP_URL to the domain being deployed
    sed -i "s|WEBAPP_URL=http://localhost:8000|WEBAPP_URL=https://${DOMAIN}|g" .env
    echo "  Created .env — edit NTFY_TOPIC before starting if you want notifications."
    echo "  (WEBAPP_URL has been set to https://${DOMAIN})"
fi

echo "==> Replacing YOUR_DOMAIN in nginx config..."
sed -i "s/YOUR_DOMAIN/${DOMAIN}/g" deploy/nginx.conf

echo "==> Obtaining initial Let's Encrypt certificate..."
# Use --standalone: certbot spins up its own temporary HTTP server on port 80.
# This avoids the chicken-and-egg problem where nginx needs certs that don't exist yet.
docker compose run --rm -p 80:80 certbot certonly --standalone \
    -d "$DOMAIN" --email "$EMAIL" \
    --agree-tos --no-eff-email

echo "==> Starting all services..."
docker compose up -d --build

echo ""
echo "Done!  Verify at: https://${DOMAIN}/"
echo "If using a cloud firewall (Hetzner, Oracle, etc.), make sure ports 80 & 443 are open there too."
