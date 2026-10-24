#!/usr/bin/env bash
# SearXNG для Open WebUI: Docker Engine внутри WSL Debian (systemd), только 127.0.0.1:8888.
# Конфиг: /opt/searxng/settings.yml (копия — settings.yml рядом; secret_key сгенерировать заново).
set -e
mkdir -p /opt/searxng
cp settings.yml /opt/searxng/settings.yml
sed -i "s|<сгенерировать: openssl rand -hex 32>|$(openssl rand -hex 32)|" /opt/searxng/settings.yml
docker run -d --name searxng --restart unless-stopped \
  -p 127.0.0.1:8888:8080 \
  -v /opt/searxng:/etc/searxng:rw \
  -e SEARXNG_BASE_URL=http://127.0.0.1:8888/ \
  searxng/searxng:latest
