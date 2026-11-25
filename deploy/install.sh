#!/usr/bin/env bash
# Install TableWatch on a mini PC (Ubuntu/Debian with systemd). Run from the repo:
#   sudo ./deploy/install.sh
# Re-run after `git pull` to update. Your config files are never overwritten.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }

apt-get install -y python3-venv curl >/dev/null
id tablewatch >/dev/null 2>&1 || useradd --system --home /opt/tablewatch --shell /usr/sbin/nologin tablewatch

mkdir -p /opt/tablewatch /etc/tablewatch
cp -r backend edge dashboard requirements*.txt /opt/tablewatch/
mkdir -p /opt/tablewatch/config
for f in floor.json zones.json; do
  [ -f /opt/tablewatch/config/$f ] || cp config/$f /opt/tablewatch/config/$f
done
[ -f /etc/tablewatch/edge.env ] || cp deploy/edge.env.example /etc/tablewatch/edge.env
chown root:tablewatch /etc/tablewatch/edge.env && chmod 640 /etc/tablewatch/edge.env

python3 -m venv /opt/tablewatch/.venv
/opt/tablewatch/.venv/bin/pip install -q -r /opt/tablewatch/requirements.txt -r /opt/tablewatch/requirements-edge.txt
cp edge/get_model.sh /opt/tablewatch/edge/ && /opt/tablewatch/edge/get_model.sh
chown -R tablewatch:tablewatch /opt/tablewatch

cp deploy/tablewatch-backend.service deploy/tablewatch-edge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tablewatch-backend tablewatch-edge
systemctl restart tablewatch-backend tablewatch-edge
echo "Installed. Edit /etc/tablewatch/edge.env and /opt/tablewatch/config/*.json, then:"
echo "  sudo systemctl restart tablewatch-backend tablewatch-edge"
echo "Dashboard: http://$(hostname -I | awk '{print $1}'):8000"
