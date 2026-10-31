#!/bin/bash
# Instalador automático para Raspberry Pi Zero 2 W / Raspberry Pi OS

set -e

echo "=========================================================="
echo " Instalador Panasonic TV Ad-Mute (Raspberry Pi)"
echo "=========================================================="

if [ "$EUID" -ne 0 ]; then
  echo "Por favor, ejecuta el instalador con privilegios sudo:"
  echo "sudo ./install.sh"
  exit 1
fi

echo "[1/4] Actualizando repositorios e instalando ADB y Python3..."
apt update -y
apt install -y adb python3 python3-pip

echo "[2/4] Copiando archivos a /opt/panasonic-tv-ad-mute..."
mkdir -p /opt/panasonic-tv-ad-mute
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp -r "$SCRIPT_DIR/raspberry_pi" /opt/panasonic-tv-ad-mute/
chmod +x /opt/panasonic-tv-ad-mute/raspberry_pi/panasonic_ad_mute.py

echo "[3/4] Instalando servicio de inicio automático (systemd)..."
cp /opt/panasonic-tv-ad-mute/raspberry_pi/panasonic-mute.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable panasonic-mute.service

echo "[4/4] Iniciando el servicio..."
systemctl restart panasonic-mute.service

echo ""
echo "=========================================================="
echo " ¡INSTALACIÓN COMPLETADA CON ÉXITO!"
echo "=========================================================="
echo "El servicio ya está activo y arrancará automáticamente con la Raspberry Pi."
echo ""
echo "Comandos útiles:"
echo " - Ver registros en tiempo real: sudo journalctl -u panasonic-mute -f"
echo " - Estado del servicio:          sudo systemctl status panasonic-mute"
echo " - Reiniciar servicio:           sudo systemctl restart panasonic-mute"
echo "=========================================================="
