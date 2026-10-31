#!/usr/bin/env python3
"""
Panasonic Google TV Ad-Mute Daemon (Raspberry Pi Zero 2 W / Linux)
Monitorea la señal del televisor por ADB y silencia la publicidad automáticamente.
"""

import os
import sys
import time
import signal
import subprocess
import threading

# Cargar configuración desde archivo o variables de entorno
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env")
CONFIG = {
    "TV_IP": "192.168.1.132:5555",
    "MUTE_DURATION": "150",
    "COOLDOWN_SECONDS": "30"
}

if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                CONFIG[k.strip()] = v.strip().strip('"').strip("'")

TV_IP = CONFIG["TV_IP"]
MUTE_DURATION = int(CONFIG["MUTE_DURATION"])
COOLDOWN_SECONDS = int(CONFIG["COOLDOWN_SECONDS"])

is_muted = False
last_mute_time = 0
running = True

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def run_adb(cmd):
    full_cmd = f"adb -s {TV_IP} {cmd}"
    try:
        subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=5)
    except Exception as e:
        log(f"Error ejecutando ADB ({cmd}): {e}")

def conectar_tv():
    log(f"Conectando a la TV ({TV_IP})...")
    subprocess.run(f"adb connect {TV_IP}", shell=True, capture_output=True, text=True, timeout=5)

def silenciar_tv(motivo="Evento detectado"):
    global is_muted, last_mute_time
    ahora = time.time()
    if is_muted:
        return
    if (ahora - last_mute_time) < COOLDOWN_SECONDS:
        return

    log(f"¡PUBLICIDAD DETECTADA! ({motivo}) -> Silenciando TV...")
    run_adb("shell input keyevent 164")
    is_muted = True
    last_mute_time = ahora

    # Iniciar temporizador para restaurar sonido
    t = threading.Thread(target=_temporizador_unmute, daemon=True)
    t.start()

def restaurar_sonido(motivo="Fin de corte publicitario"):
    global is_muted
    if not is_muted:
        return
    log(f"Restaurando sonido de la TV ({motivo})...")
    run_adb("shell input keyevent 164")
    is_muted = False

def _temporizador_unmute():
    global is_muted
    time.sleep(MUTE_DURATION)
    if is_muted:
        restaurar_sonido(motivo=f"Tiempo cumplido ({MUTE_DURATION}s)")

def manejar_salida(signum, frame):
    global running, is_muted
    log("Señal de terminación recibida. Restaurando volumen si estaba silenciada...")
    running = False
    if is_muted:
        run_adb("shell input keyevent 164")
    sys.exit(0)

def main():
    global running
    signal.signal(signal.SIGINT, manejar_salida)
    signal.signal(signal.SIGTERM, manejar_salida)

    log("=======================================================")
    log(" Servicio Panasonic Ad-Mute iniciado en Raspberry Pi ")
    log(f" Objetivo TV: {TV_IP} | Tiempo silencio: {MUTE_DURATION}s")
    log("=======================================================")

    while running:
        try:
            conectar_tv()
            # Limpiar buffer de logs previos
            subprocess.run(f"adb -s {TV_IP} logcat -c", shell=True)

            cmd = [
                "adb", "-s", TV_IP, "logcat", "-v", "time",
                "MtkTvHBBTVBase:D",
                "AUDIO_AMP:W",
                "*:S"
            ]

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            for line in proc.stdout:
                if not running:
                    break
                line_str = line.strip()
                if not line_str:
                    continue

                # Patrones de entrada de corte publicitario HbbTV / Señal de audio
                if "exchangeType==28" in line_str or "getHBBTVBannerControl" in line_str:
                    silenciar_tv(motivo="Marcador HbbTV")

            proc.terminate()

        except Exception as e:
            log(f"Aviso en bucle de escucha: {e}. Reintentando en 10s...")
            time.sleep(10)

if __name__ == "__main__":
    main()
