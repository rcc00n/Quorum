#!/usr/bin/env bash
# Run on the VPS after the inspection and first-install TLS gates in README.md.
set -euo pipefail
release=${1:?Usage: install-release.sh /opt/quorum/releases/RELEASE}
case "$release" in /opt/quorum/releases/*) ;; *) exit 2 ;; esac
test -f "$release/web/server.js"
test -f /etc/quorum/portal.env
install -d -m 755 /opt/quorum/static
test -f /etc/letsencrypt/live/quorum.raccncode.com/fullchain.pem
if [[ -e /opt/quorum/current || -L /opt/quorum/current ]]; then
  echo 'Existing release: back up the database and follow the update procedure first.' >&2
  exit 2
fi
for unit in quorum-api quorum-web; do
  test ! -e "/etc/systemd/system/$unit.service"
done
python3 - <<'PY'
import socket
for port in (3017,8017):
    with socket.socket() as s:
        s.bind(('127.0.0.1',port))
PY
# Refuse an unknown vhost; only the exact first-install bootstrap is accepted.
python3 - <<'PY'
from pathlib import Path
text=Path('/etc/nginx/conf.d/quorum.conf').read_text()
expected='''server {
 listen 80;
 listen [::]:80;
 server_name quorum.raccncode.com;
 location /.well-known/acme-challenge/ { root /var/www/certbot; }
 location / { return 503; }
}
'''
if text != expected: raise SystemExit('Quorum bootstrap vhost differs; inspect before modifying')
PY
ln -s "$release" /opt/quorum/current
set -a
source /etc/quorum/portal.env
set +a
/opt/quorum/venv/bin/python "$release/backend/manage.py" migrate --noinput
/opt/quorum/venv/bin/python "$release/backend/manage.py" check --deploy
/opt/quorum/venv/bin/python "$release/backend/manage.py" collectstatic --noinput
chown -R quorum:quorum /var/lib/quorum
chmod 750 /var/lib/quorum
chmod 640 /var/lib/quorum/portal.sqlite3
install -m 644 "$release/deploy/quorum-api.service" /etc/systemd/system/quorum-api.service
install -m 644 "$release/deploy/quorum-web.service" /etc/systemd/system/quorum-web.service
systemctl daemon-reload
systemctl enable --now quorum-api quorum-web
install -m 644 "$release/deploy/quorum.nginx.conf" /etc/nginx/conf.d/quorum.conf
nginx -t
systemctl reload nginx
# Certbot invokes deploy hooks only after successful renewal; this hook changes no vhost.
install -d /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/quorum-reload <<'EOF'
#!/bin/sh
case "$RENEWED_LINEAGE" in
 /etc/letsencrypt/live/quorum.raccncode.com) /usr/sbin/nginx -t && /bin/systemctl reload nginx ;;
esac
EOF
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/quorum-reload
systemctl is-active quorum-api quorum-web
