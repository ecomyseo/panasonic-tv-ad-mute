#!/bin/bash
# Instalador del Panasonic TV Hub para Raspberry Pi (Raspberry Pi OS Lite, Bookworm o Trixie)
#
#   sudo ./install.sh [--tv-ip 192.168.1.132] [--tv-mac AA:BB:CC:DD:EE:FF] [--usuario pi]
#                     [--sin-apt] [--sin-parear]
#
# Instala en /opt/panasonic-tv-hub, deja la configuración en /etc/panasonic-tv-hub/config.env
# (no se pisa al actualizar) y crea dos servicios: panasonic-mute (silenciador) y panasonic-web
# (mando web). Se puede volver a ejecutar para actualizar.
#
# TVHUB_RAIZ=<carpeta> solo para pruebas: instala todo bajo esa carpeta y no toca el sistema.

set -euo pipefail

RAIZ="${TVHUB_RAIZ:-}"
RUTA_REAL="/opt/panasonic-tv-hub"
DESTINO="$RAIZ$RUTA_REAL"
CONF_DIR="$RAIZ/etc/panasonic-tv-hub"
ESTADO_DIR="$RAIZ/var/lib/panasonic-tv-hub"
SYSTEMD_DIR="$RAIZ/etc/systemd/system"
JOURNALD_DIR="$RAIZ/etc/systemd/journald.conf.d"
BIN_DIR="$RAIZ/usr/local/bin"
ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TV_IP_NUEVA=""
TV_MAC_NUEVA=""
USUARIO=""
CON_APT=1
CON_PAREO=1

while [ $# -gt 0 ]; do
  case "$1" in
    --tv-ip)    TV_IP_NUEVA="${2:-}"; shift 2 ;;
    --tv-mac)   TV_MAC_NUEVA="${2:-}"; shift 2 ;;
    --usuario)  USUARIO="${2:-}"; shift 2 ;;
    --sin-apt)  CON_APT=0; shift ;;
    --sin-parear) CON_PAREO=0; shift ;;
    -h|--help)  sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $1"; exit 1 ;;
  esac
done

if [ -z "$RAIZ" ] && [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta el instalador con sudo:  sudo ./install.sh"
  exit 1
fi

# Usuario de los servicios: el que lanza sudo (su llave ADB es la que la TV autoriza)
if [ -z "$USUARIO" ]; then
  USUARIO="${SUDO_USER:-}"
fi
if [ -z "$USUARIO" ] || [ "$USUARIO" = "root" ]; then
  USUARIO="$(getent passwd 1000 | cut -d: -f1 || true)"
fi
if [ -z "$USUARIO" ] || ! id "$USUARIO" >/dev/null 2>&1; then
  echo "No encuentro el usuario de la Raspberry. Indícalo con: sudo ./install.sh --usuario <nombre>"
  exit 1
fi
GRUPO="$(id -gn "$USUARIO")"

if [ -n "$TV_IP_NUEVA" ] && [[ "$TV_IP_NUEVA" != *:* ]]; then
  TV_IP_NUEVA="$TV_IP_NUEVA:5555"
fi

echo "=========================================================="
echo " Panasonic TV Hub - instalación en Raspberry Pi"
echo " Usuario de los servicios: $USUARIO"
echo "=========================================================="

# ---------------------------------------------------------------------------
echo "[1/6] Paquetes del sistema (adb y python3)..."
if [ "$CON_APT" -eq 1 ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends adb python3
else
  echo "      (omitido con --sin-apt)"
fi

# ---------------------------------------------------------------------------
echo "[2/6] Copiando el programa a $RUTA_REAL..."
NUEVO="$DESTINO.nuevo"
rm -rf "$NUEVO"
mkdir -p "$NUEVO"
for elemento in core raspberry_pi avisos_app web_remote.py menu_tv.py README.md COMPATIBILIDAD.md LICENSE privado; do
  if [ -e "$ORIGEN/$elemento" ]; then
    cp -r "$ORIGEN/$elemento" "$NUEVO/"
  fi
done
find "$NUEVO" -name "__pycache__" -type d -prune -exec rm -rf {} +
if [ -d "$DESTINO" ]; then
  rm -rf "$DESTINO.viejo"
  mv "$DESTINO" "$DESTINO.viejo"
fi
mv "$NUEVO" "$DESTINO"
rm -rf "$DESTINO.viejo"
chmod 755 "$DESTINO/raspberry_pi/panasonic_ad_mute.py" "$DESTINO/web_remote.py" "$DESTINO/menu_tv.py"
if [ -d "$DESTINO/privado" ]; then
  # Módulo privado de WhatsApp: solo lo lee el usuario de los servicios
  chown -R "$USUARIO:$GRUPO" "$DESTINO/privado"
  chmod 700 "$DESTINO/privado"
  find "$DESTINO/privado" -type f -exec chmod 600 {} +
fi
# Restos del instalador antiguo
if [ -z "$RAIZ" ] && [ -d /opt/panasonic-tv-ad-mute ]; then
  rm -rf /opt/panasonic-tv-ad-mute
fi

# ---------------------------------------------------------------------------
echo "[3/6] Configuración en /etc/panasonic-tv-hub/config.env..."
mkdir -p "$CONF_DIR" "$ESTADO_DIR"
if [ ! -f "$CONF_DIR/config.env" ]; then
  cp "$DESTINO/raspberry_pi/config.env" "$CONF_DIR/config.env"
  echo "      Creada a partir de la plantilla."
else
  echo "      Se conserva la configuración existente."
  # Claves nuevas de la plantilla que aún no estén en la configuración del usuario
  while IFS= read -r linea; do
    clave="${linea%%=*}"
    if [ -n "$clave" ] && ! grep -qE "^$clave=" "$CONF_DIR/config.env"; then
      echo "$linea" >> "$CONF_DIR/config.env"
      echo "      Añadida la opción nueva $clave"
    fi
  done < <(grep -E '^[A-Z_]+=' "$DESTINO/raspberry_pi/config.env")
fi
if [ -n "$TV_IP_NUEVA" ]; then
  sed -i "s|^TV_IP=.*|TV_IP=$TV_IP_NUEVA|" "$CONF_DIR/config.env"
fi
if [ -n "$TV_MAC_NUEVA" ]; then
  sed -i "s|^TV_MAC=.*|TV_MAC=$TV_MAC_NUEVA|" "$CONF_DIR/config.env"
fi
chown "root:$GRUPO" "$CONF_DIR/config.env"
chmod 640 "$CONF_DIR/config.env"
chown "$USUARIO:$GRUPO" "$ESTADO_DIR"
TV_IP="$(grep -E '^TV_IP=' "$CONF_DIR/config.env" | tail -1 | cut -d= -f2- | tr -d "\"'" || true)"
echo "      TV configurada: $TV_IP"

# ---------------------------------------------------------------------------
echo "[4/6] Servicios de arranque automático y orden 'tvhub'..."
mkdir -p "$SYSTEMD_DIR" "$JOURNALD_DIR" "$BIN_DIR"
for unidad in panasonic-mute.service panasonic-web.service; do
  sed -e "s|@USUARIO@|$USUARIO|g" -e "s|@DESTINO@|$RUTA_REAL|g" \
    "$DESTINO/raspberry_pi/$unidad" > "$SYSTEMD_DIR/$unidad"
done
sed -e "s|@USUARIO@|$USUARIO|g" -e "s|@DESTINO@|$RUTA_REAL|g" \
  "$DESTINO/raspberry_pi/tvhub" > "$BIN_DIR/tvhub"
chmod 755 "$BIN_DIR/tvhub"
# El registro del sistema no pasa de 30 MB: cuida la tarjeta SD
cat > "$JOURNALD_DIR/panasonic-tv-hub.conf" <<'CONF'
[Journal]
SystemMaxUse=30M
CONF

# ---------------------------------------------------------------------------
echo "[5/6] Conexión con la TV ($TV_IP)..."
como_usuario() {
  if [ -n "$RAIZ" ]; then "$@"; else sudo -u "$USUARIO" -H "$@"; fi
}
estado_adb() {
  como_usuario adb devices 2>/dev/null | awk -v ip="$TV_IP" '$1==ip{print $2}' || true
}
ESTADO_TV="sin_conexion"
if [ "$CON_PAREO" -eq 1 ] && command -v adb >/dev/null 2>&1; then
  como_usuario timeout 15 adb connect "$TV_IP" || true
  ESTADO_TV="$(estado_adb)"
  if [ "$ESTADO_TV" = "unauthorized" ] || [ "$ESTADO_TV" = "offline" ]; then
    echo "      >>> Mira la TV: marca «Permitir siempre» y pulsa Aceptar en el aviso de depuración."
    for _ in $(seq 1 30); do
      sleep 2
      ESTADO_TV="$(estado_adb)"
      [ "$ESTADO_TV" = "device" ] && break
    done
  fi
  case "$ESTADO_TV" in
    device) echo "      TV conectada y autorizada." ;;
    unauthorized) echo "      Falta aceptar el aviso en la TV. Cuando puedas: tvhub parear" ;;
    *) echo "      La TV no responde ahora (¿apagada o en otra IP?). Más tarde: tvhub parear" ;;
  esac
else
  echo "      (omitido)"
fi

# ---------------------------------------------------------------------------
echo "[6/6] Arrancando los servicios..."
if [ -z "$RAIZ" ]; then
  systemctl daemon-reload
  systemctl restart systemd-journald || true
  systemctl enable panasonic-mute.service panasonic-web.service
  systemctl restart panasonic-mute.service panasonic-web.service
  sleep 3
  for s in panasonic-mute panasonic-web; do
    printf "      %-15s %s\n" "$s" "$(systemctl is-active "$s" || true)"
  done
else
  echo "      (modo prueba: no se tocan los servicios)"
fi

IP_PI="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
PUERTO="$(grep -E '^WEB_PORT=' "$CONF_DIR/config.env" | tail -1 | cut -d= -f2- | tr -d "\"'" || true)"
echo ""
echo "=========================================================="
echo " INSTALACIÓN TERMINADA"
echo "=========================================================="
echo " Mando web en el móvil:  http://${IP_PI:-IP_DE_LA_RASPBERRY}:${PUERTO:-8080}"
echo "                         http://$(hostname 2>/dev/null || echo raspberrypi).local:${PUERTO:-8080}"
echo " Menú en la consola:     tvhub"
echo " Estado y registro:      tvhub estado  |  tvhub logs"
echo " Cambiar la IP de la TV: tvhub config"
echo "=========================================================="
