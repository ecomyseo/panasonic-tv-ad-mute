#!/bin/bash
# Desinstala el Panasonic TV Hub de la Raspberry Pi.
#   sudo ./uninstall.sh          conserva /etc/panasonic-tv-hub y /var/lib/panasonic-tv-hub
#   sudo ./uninstall.sh --todo   lo borra todo
set -euo pipefail

RAIZ="${TVHUB_RAIZ:-}"
if [ -z "$RAIZ" ] && [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta con sudo:  sudo ./uninstall.sh"
  exit 1
fi

if [ -z "$RAIZ" ]; then
  systemctl disable --now panasonic-mute.service panasonic-web.service 2>/dev/null || true
fi
rm -f "$RAIZ/etc/systemd/system/panasonic-mute.service" "$RAIZ/etc/systemd/system/panasonic-web.service"
rm -f "$RAIZ/usr/local/bin/tvhub" "$RAIZ/etc/systemd/journald.conf.d/panasonic-tv-hub.conf"
rm -rf "$RAIZ/opt/panasonic-tv-hub"
if [ "${1:-}" = "--todo" ]; then
  rm -rf "$RAIZ/etc/panasonic-tv-hub" "$RAIZ/var/lib/panasonic-tv-hub"
  echo "Desinstalado por completo."
else
  echo "Desinstalado. La configuración sigue en /etc/panasonic-tv-hub (bórrala con --todo)."
fi
if [ -z "$RAIZ" ]; then
  systemctl daemon-reload
fi
