#!/usr/bin/env bash
# Запускать на сервере в /opt/shkola21-dashboard после распаковки архива.
set -euo pipefail

APP_DIR="/opt/shkola21-dashboard"
cd "$APP_DIR"

if [ ! -f requirements.txt ]; then
  echo "Ошибка: запустите из папки проекта (должен быть requirements.txt)"
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан .env из .env.example — отредактируйте: nano .env"
fi

python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt

cat > /etc/systemd/system/shkola21.service << EOF
[Unit]
Description=Shkola21 Dashboard
After=network.target

[Service]
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8010
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/nginx/sites-available/shkola21 << 'NGINX'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/shkola21 /etc/nginx/sites-enabled/shkola21
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable --now shkola21
nginx -t && systemctl reload nginx

echo ""
echo "Готово. Откройте в браузере: http://$(curl -fsS ifconfig.me 2>/dev/null || echo 'ВАШ_IP')"
echo "Проверка API: curl -s http://127.0.0.1:8010/api/health"
curl -s http://127.0.0.1:8010/api/health || true
echo ""
echo "Если .env не настроен — nano ${APP_DIR}/.env && systemctl restart shkola21"
