#!/data/data/com.termux/files/usr/bin/bash
# Panasonic TV Hub en un móvil Android, con Termux (sin root y sin cables).
#
# En Termux, una sola orden:
#   curl -sL https://raw.githubusercontent.com/ecomyseo/panasonic-tv-ad-mute/master/termux/instalar.sh | bash -s 192.168.1.132
# (la IP es la de la tele; si no se pone, se usa la de raspberry_pi/config.env)
#
# Deja el hub en ~/panasonic-tv-hub, sus ajustes y su estado en ~/.panasonic-tv-hub, lo arranca, y con la app
# Termux:Boot lo arranca solo cada vez que se encienda el móvil. Volver a lanzarlo lo pone al día sin tocar los ajustes.
set -e

REPO="ecomyseo/panasonic-tv-ad-mute"
DESTINO="$HOME/panasonic-tv-hub"
DATOS="$HOME/.panasonic-tv-hub"
TV_IP="${1:-}"

if [ -z "$PREFIX" ] || [ ! -d "/data/data/com.termux" ]; then
    echo "Esto se ejecuta dentro de Termux, en el móvil." >&2
    exit 1
fi

echo "== 1/5 Programas (python, adb y rclone)"
export DEBIAN_FRONTEND=noninteractive
# upgrade y no update: con un Termux recién instalado, instalar sin poner al día lo que ya trae deja programas
# que no arrancan («cannot locate symbol SSL_...», visto en un Umidigi el 3/11/2026)
# Va sin salida por pantalla: se dice qué está haciendo para que no parezca colgado (5/11/2026).
echo "   poniendo al día Termux (puede tardar varios minutos; no lo cortes)..."
yes | pkg upgrade -y -o Dpkg::Options::=--force-confnew >/dev/null 2>&1 || true
echo "   python y adb..."
pkg install -y -o Dpkg::Options::=--force-confnew python android-tools curl tar >/dev/null
command -v python >/dev/null && command -v adb >/dev/null || { echo "No se han instalado python o adb." >&2; exit 1; }
# rclone: la pasarela SFTP del NAS (core/nas_pasarela.py). Si no se instala, el resto del hub sigue igual.
echo "   rclone (la primera vez baja unos 20 MB)..."
pkg install -y -o Dpkg::Options::=--force-confnew rclone >/dev/null 2>&1 || echo "Aviso: no se ha podido instalar rclone (la pasarela del NAS no arrancará)."

TEMPORAL="$(mktemp -d)"
mkdir -p "$TEMPORAL/hub"
# Lanzado desde una copia del repositorio (git clone ...; bash panasonic-tv-ad-mute/termux/instalar.sh), se usa esa
ORIGEN="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." 2>/dev/null && pwd)"
if [ -f "$ORIGEN/raspberry_pi/panasonic_ad_mute.py" ] && [ "$ORIGEN" != "$DESTINO" ]; then
    echo "== 2/5 El hub (de $ORIGEN)"
    (cd "$ORIGEN" && tar -cf - --exclude=.git .) | tar -xf - -C "$TEMPORAL/hub"
else
    echo "== 2/5 El hub (de GitHub)"
    curl -sfL "https://codeload.github.com/$REPO/tar.gz/refs/heads/master" -o "$TEMPORAL/hub.tar.gz"
    tar -xzf "$TEMPORAL/hub.tar.gz" -C "$TEMPORAL/hub" --strip-components=1
fi
[ -f "$TEMPORAL/hub/raspberry_pi/panasonic_ad_mute.py" ] || { echo "La descarga no trae el hub." >&2; exit 1; }
"$HOME/panasonic-tv-hub/termux/parar.sh" >/dev/null 2>&1 || true
rm -rf "$DESTINO.nuevo"
mv "$TEMPORAL/hub" "$DESTINO.nuevo"
rm -rf "$DESTINO"
mv "$DESTINO.nuevo" "$DESTINO"
rm -rf "$TEMPORAL"
chmod +x "$DESTINO"/termux/*.sh

echo "== 3/5 Ajustes (en $DATOS, no se pisan al actualizar)"
mkdir -p "$DATOS/estado"
if [ ! -f "$DATOS/config.env" ]; then
    cp "$DESTINO/raspberry_pi/config.env" "$DATOS/config.env"
    echo "STATE_DIR=$DATOS/estado" >> "$DATOS/config.env"
fi
if [ -n "$TV_IP" ]; then
    case "$TV_IP" in *:*) ;; *) TV_IP="$TV_IP:5555" ;; esac
    if grep -q '^TV_IP=' "$DATOS/config.env"; then
        sed -i "s|^TV_IP=.*|TV_IP=$TV_IP|" "$DATOS/config.env"
    else
        echo "TV_IP=$TV_IP" >> "$DATOS/config.env"
    fi
fi
# El DNS antirrastreo necesita el puerto 53, que en un móvil sin root no se puede abrir
sed -i 's|^DNS_ACTIVO=.*|DNS_ACTIVO=0|' "$DATOS/config.env"

echo "== 4/5 Arranque solo al encender el móvil (app Termux:Boot)"
mkdir -p "$HOME/.termux/boot"
cat > "$HOME/.termux/boot/panasonic-tv-hub" <<EOF
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
"$DESTINO/termux/arrancar.sh"
EOF
chmod +x "$HOME/.termux/boot/panasonic-tv-hub"

echo "== 5/5 Arrancando"
termux-wake-lock 2>/dev/null || true
"$DESTINO/termux/arrancar.sh"

IP_MOVIL="$(ip -4 addr show wlan0 2>/dev/null | sed -n 's/.*inet \([0-9.]*\).*/\1/p' | head -1)"
echo
echo "Listo. Mando en el navegador: http://${IP_MOVIL:-<IP del móvil>}:8080"
echo "La tele puede preguntar «¿Permitir la depuración?»: acéptalo con el mando y marca «Permitir siempre»."
echo "Para que no se pare: Ajustes del móvil > Aplicaciones > Termux > Batería > Sin restricciones."
