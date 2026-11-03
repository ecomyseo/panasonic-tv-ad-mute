#!/data/data/com.termux/files/usr/bin/bash
# Arranca el silenciador y el mando web del hub en Termux, cada uno en un bucle que lo relanza si se cae.
# No arranca otro si ya están en marcha.
DESTINO="$HOME/panasonic-tv-hub"
DATOS="$HOME/.panasonic-tv-hub"
export TVHUB_CONFIG="$DATOS/config.env"
export PYTHONUNBUFFERED=1
mkdir -p "$DATOS/estado"

vigilar() {  # vigilar <nombre> <script>
    local nombre="$1" script="$2"
    if [ -f "$DATOS/$nombre.pid" ] && kill -0 "$(cat "$DATOS/$nombre.pid")" 2>/dev/null; then
        echo "$nombre ya está en marcha"
        return
    fi
    nohup bash -c "
        while [ ! -f '$DATOS/parar' ]; do
            python '$DESTINO/$script' >> '$DATOS/$nombre.log' 2>&1 &
            echo \$! > '$DATOS/$nombre.hijo'
            wait \$!
            [ -f '$DATOS/parar' ] && break
            echo \"[\$(date '+%F %T')] $nombre se ha parado; lo vuelvo a arrancar en 10 s\" >> '$DATOS/$nombre.log'
            sleep 10
        done
    " >/dev/null 2>&1 &
    echo $! > "$DATOS/$nombre.pid"
    echo "$nombre arrancado"
}

rm -f "$DATOS/parar"
cd "$DESTINO" || exit 1
for registro in silenciador web; do  # que los registros no crezcan sin fin
    [ -f "$DATOS/$registro.log" ] && [ "$(wc -c < "$DATOS/$registro.log")" -gt 2000000 ] \
        && mv "$DATOS/$registro.log" "$DATOS/$registro.log.1"
done
vigilar silenciador raspberry_pi/panasonic_ad_mute.py
vigilar web web_remote.py
