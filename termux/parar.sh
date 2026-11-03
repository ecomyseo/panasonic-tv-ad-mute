#!/data/data/com.termux/files/usr/bin/bash
# Para el hub en Termux (el silenciador, el mando web y sus bucles de vigilancia).
DATOS="$HOME/.panasonic-tv-hub"
mkdir -p "$DATOS"
touch "$DATOS/parar"
for nombre in silenciador web; do
    for fichero in "$DATOS/$nombre.pid" "$DATOS/$nombre.hijo"; do  # el bucle que vigila y el programa
        if [ -f "$fichero" ]; then
            kill "$(cat "$fichero")" 2>/dev/null
            rm -f "$fichero"
        fi
    done
done
pkill -f "panasonic-tv-hub/raspberry_pi/panasonic_ad_mute.py" 2>/dev/null
pkill -f "panasonic-tv-hub/web_remote.py" 2>/dev/null
echo "Hub parado. Para volver a arrancarlo: ~/panasonic-tv-hub/termux/arrancar.sh"
