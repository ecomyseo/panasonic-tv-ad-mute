import subprocess
import time

TV_IP = "192.168.1.132:5555"

def conectar():
    subprocess.run(f"adb connect {TV_IP}", shell=True, capture_output=True, text=True, timeout=5)

def monitor_eventos():
    conectar()
    print("=" * 65)
    print(" MONITOR DE EVENTOS EN TIEMPO REAL (WINDOWS)")
    print("=" * 65)
    print("Conectado a la TV en 192.168.1.132.")
    print("Viendo eventos de señal, audio y HbbTV...")
    print("Presiona Ctrl+C para detener el monitor.\n")
    print("-" * 65)

    subprocess.run(f"adb -s {TV_IP} logcat -c", shell=True)

    cmd = [
        "adb", "-s", TV_IP, "logcat", "-v", "time",
        "MtkTvHBBTVBase:D",
        "MtkTvHBBTV_jni:D",
        "AUDIO_AMP:W",
        "TV_MtkTvAVModeBase:I",
        "MtkTvChannelList_jni:D",
        "*:S"
    ]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        for line in proc.stdout:
            line_str = line.strip()
            if not line_str:
                continue

            if "getHBBTVBannerControl" in line_str:
                print(f"[{time.strftime('%H:%M:%S')}] [SEÑAL HBBTV] Banner / Inserción publicitaria consultada.")
            elif "exchangeType==28" in line_str:
                print(f"[{time.strftime('%H:%M:%S')}] [SEÑAL HBBTV] Datos de corte comercial intercambiados.")
            elif "AUDIO_AMP" in line_str or "Set volume to handle" in line_str:
                print(f"[{time.strftime('%H:%M:%S')}] [SEÑAL AUDIO] Reconfiguración del procesador de audio detectada.")
            elif "name--" in line_str:
                canal = line_str.split("name--")[-1].split("...")[0]
                print(f"[{time.strftime('%H:%M:%S')}] [CANAL] Canal sintonizado: {canal}")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] {line_str}")

    except KeyboardInterrupt:
        print("\n\nMonitor detenido.")
    finally:
        if 'proc' in locals():
            proc.terminate()

if __name__ == "__main__":
    monitor_eventos()
