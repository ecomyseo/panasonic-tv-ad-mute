import subprocess
import time
import sys
import threading

TV_IP = "192.168.1.132:5555"
MUTE_DURATION_SECONDS = 150
COOLDOWN_SECONDS = 30

is_muted = False
last_mute_time = 0

def run_adb(cmd: str):
    subprocess.run(f"adb -s {TV_IP} {cmd}", shell=True, capture_output=True, text=True, timeout=5)

def conectar():
    subprocess.run(f"adb connect {TV_IP}", shell=True, capture_output=True, text=True, timeout=5)

def silenciar_tv(motivo="Evento detectado"):
    global is_muted, last_mute_time
    ahora = time.time()
    if is_muted:
        return
    if (ahora - last_mute_time) < COOLDOWN_SECONDS:
        return

    print(f"\n[{time.strftime('%H:%M:%S')}] ¡PUBLICIDAD DETECTADA! ({motivo})")
    print(f"[{time.strftime('%H:%M:%S')}] -> Silenciando la TV automáticamente...")
    run_adb("shell input keyevent 164")
    is_muted = True
    last_mute_time = ahora

    threading.Thread(target=_temporizador_unmute, daemon=True).start()

def restaurar_sonido(motivo="Fin de bloque"):
    global is_muted
    if not is_muted:
        return
    print(f"\n[{time.strftime('%H:%M:%S')}] Fin de publicidad ({motivo}). Restaurando sonido...")
    run_adb("shell input keyevent 164")
    is_muted = False

def _temporizador_unmute():
    global is_muted
    time.sleep(MUTE_DURATION_SECONDS)
    if is_muted:
        restaurar_sonido(motivo="Tiempo máximo cumplido")

def bucle_deteccion():
    conectar()
    print("=" * 65)
    print(" SERVICIO DE SILENCIADO AUTOMÁTICO DE PUBLICIDAD (WINDOWS)")
    print("=" * 65)
    print("Escuchando eventos de la señal en Panasonic Google TV (192.168.1.132)...")
    print("El sistema silenciará la tele automáticamente cuando detecte la señal.")
    print("Presiona Ctrl+C para detener el servicio.\n")

    subprocess.run(f"adb -s {TV_IP} logcat -c", shell=True)

    cmd = [
        "adb", "-s", TV_IP, "logcat", "-v", "time",
        "MtkTvHBBTVBase:D",
        "AUDIO_AMP:W",
        "*:S"
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        for line in proc.stdout:
            line_str = line.strip()
            if not line_str:
                continue

            if "exchangeType==28" in line_str or "getHBBTVBannerControl" in line_str:
                silenciar_tv(motivo="Marcador HbbTV de Publicidad")

    except KeyboardInterrupt:
        print("\n\nServicio detenido.")
        if is_muted:
            restaurar_sonido("Cierre de servicio")
    finally:
        if 'proc' in locals():
            proc.terminate()

if __name__ == "__main__":
    bucle_deteccion()
