import subprocess
import time
import sys

TV_IP = "192.168.1.132:5555"

def run_adb(command: str) -> str:
    """Ejecuta un comando ADB contra la TV Panasonic."""
    full_cmd = f"adb -s {TV_IP} {command}"
    try:
        res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=5)
        return res.stdout.strip()
    except Exception as e:
        return f"Error: {e}"

def conectar():
    """Asegura la conexión con la TV por ADB."""
    subprocess.run(f"adb connect {TV_IP}", shell=True, capture_output=True, text=True, timeout=5)

def toggle_mute():
    """Alterna el silencio de la TV mediante KEYCODE_VOLUME_MUTE (164)."""
    conectar()
    run_adb("shell input keyevent 164")
    print("[OK] Comando de silencio alternado en la TV.")

def subir_volumen():
    conectar()
    run_adb("shell input keyevent 24")
    print("[OK] Volumen subido.")

def bajar_volumen():
    conectar()
    run_adb("shell input keyevent 25")
    print("[OK] Volumen bajado.")

def obtener_canal_actual():
    """Consulta el canal TDT sintonizado en la TV a través de los logs de MediaTek."""
    conectar()
    out = run_adb("shell logcat -d -t 60")
    for line in reversed(out.splitlines()):
        if "name--" in line:
            partes = line.split("name--")
            if len(partes) > 1:
                canal = partes[1].split("...")[0].strip()
                return canal
    return "Canal TDT (No identificado)"

def modo_anuncios(segundos=150):
    """Silencia la TV de inmediato y restaura el sonido automáticamente."""
    conectar()
    canal = obtener_canal_actual()
    print("=" * 55)
    print(f" MODO PUBLICIDAD ACTIVADO ({canal})")
    print(f" Silenciando la TV durante {segundos} segundos...")
    print("=" * 55)
    
    run_adb("shell input keyevent 164")
    
    try:
        for restante in range(segundos, 0, -1):
            sys.stdout.write(f"\r[Publicidad] Tiempo restante de silencio: {restante:3d}s (Ctrl+C para cancelar) ")
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[Cancelado] Restaurando sonido manualmente...")
    
    run_adb("shell input keyevent 164")
    print("\n[OK] ¡Fin de publicidad! Sonido restaurado automáticamente.\n")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg == "mute":
            toggle_mute()
        elif arg in ("anuncio", "publi"):
            secs = int(sys.argv[2]) if len(sys.argv) > 2 else 150
            modo_anuncios(secs)
        elif arg == "up":
            subir_volumen()
        elif arg == "down":
            bajar_volumen()
        elif arg == "canal":
            print(f"Canal actual en pantalla: {obtener_canal_actual()}")
    else:
        conectar()
        print("\n" + "=" * 50)
        print(" CONTROL PANASONIC GOOGLE TV DESDE WINDOWS")
        print("=" * 50)
        print(f" Canal actual: {obtener_canal_actual()}")
        print("-" * 50)
        print(" 1. Silenciar / Restaurar volumen (MUTE)")
        print(" 2. Modo Publicidad (Silenciar 2 min y medio y volver)")
        print(" 3. Modo Publicidad personalizada (indicar segundos)")
        print(" 4. Subir volumen")
        print(" 5. Bajar volumen")
        print(" 0. Salir")
        print("-" * 50)
        op = input("Elige una opción: ").strip()
        if op == "1":
            toggle_mute()
        elif op == "2":
            modo_anuncios(150)
        elif op == "3":
            s = input("¿Cuántos segundos dura el corte? [Ej: 120]: ").strip()
            modo_anuncios(int(s) if s.isdigit() else 150)
        elif op == "4":
            subir_volumen()
        elif op == "5":
            bajar_volumen()
