"""
Panasonic Google TV ADB Core Manager
Controlador completo para televisores Panasonic con Android TV / Google TV.
"""

import subprocess
import time
import os
import threading

class PanasonicTVManager:
    def __init__(self, tv_ip="192.168.1.132:5555"):
        self.tv_ip = tv_ip
        self.is_muted = False
        self.sleep_timer_thread = None
        self.cancel_sleep = False

    def adb(self, cmd: str, timeout=5) -> str:
        """Ejecuta un comando ADB contra la TV."""
        full_cmd = f"adb -s {self.tv_ip} {cmd}"
        try:
            res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return res.stdout.strip()
        except Exception as e:
            return f"Error: {e}"

    def connect(self) -> bool:
        """Asegura la conexión con la TV por ADB."""
        res = subprocess.run(f"adb connect {self.tv_ip}", shell=True, capture_output=True, text=True, timeout=5)
        return "connected" in res.stdout or "already connected" in res.stdout

    # --- CONTROL DE AUDIO Y MUTE ---
    def toggle_mute(self) -> str:
        self.adb("shell input keyevent 164")
        self.is_muted = not self.is_muted
        return "Silencio alternado"

    def volume_up(self) -> str:
        self.adb("shell input keyevent 24")
        return "Volumen +"

    def volume_down(self) -> str:
        self.adb("shell input keyevent 25")
        return "Volumen -"

    # --- NAVEGACIÓN Y MANDO A DISTANCIA ---
    def key_power(self) -> str:
        self.adb("shell input keyevent 26")
        return "Encendido / Apagado (Standby)"

    def key_home(self) -> str:
        self.adb("shell input keyevent 3")
        return "Inicio (Home)"

    def key_back(self) -> str:
        self.adb("shell input keyevent 4")
        return "Volver (Back)"

    def key_dpad(self, direction: str) -> str:
        mapping = {
            "up": 19,
            "down": 20,
            "left": 21,
            "right": 22,
            "enter": 66,
            "ok": 66
        }
        code = mapping.get(direction.lower(), 66)
        self.adb(f"shell input keyevent {code}")
        return f"Tecla {direction.upper()} enviada"

    def send_text(self, text: str) -> str:
        """Envía texto o contraseñas directamente al campo activo de la TV."""
        # Reemplazar espacios por %s para ADB
        safe_text = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
        self.adb(f"shell input text '{safe_text}'")
        return f"Texto enviado: {text}"

    # --- APLICACIONES Y STREAMING ---
    def get_known_apps(self) -> dict:
        return {
            "YouTube": "com.google.android.youtube.tv/com.google.android.apps.youtube.tv.activity.ShellActivity",
            "YouTube Music": "com.google.android.youtube.tvmusic",
            "Netflix": "com.netflix.ninja/.MainActivity",
            "Movistar+": "com.movistarplus.androidtv",
            "Atresplayer": "com.antena3.atresplayer.tv",
            "RTVE Play": "com.rtve.androidtv",
            "Tivify": "com.tvup.tivify.app.tv",
            "TDT Live TV": "com.mediatek.wwtv.tvcenter/.nav.TurnkeyUiMainActivity"
        }

    def launch_app(self, package_or_alias: str) -> str:
        apps = self.get_known_apps()
        target = apps.get(package_or_alias, package_or_alias)
        if "/" in target:
            self.adb(f"shell am start -n {target}")
        else:
            self.adb(f"shell monkey -p {target} -c android.intent.category.LAUNCHER 1")
        return f"Lanzando {package_or_alias}..."

    # --- INFORMACIÓN Y DIAGNÓSTICO EN TIEMPO REAL ---
    def get_current_channel(self) -> str:
        out = self.adb("shell logcat -d -t 60")
        for line in reversed(out.splitlines()):
            if "name--" in line:
                partes = line.split("name--")
                if len(partes) > 1:
                    return partes[1].split("...")[0].strip()
        return "TDT / Desconocido"

    def get_tv_stats(self) -> dict:
        model = self.adb("shell getprop ro.product.model")
        android_ver = self.adb("shell getprop ro.build.version.release")
        uptime = self.adb("shell uptime")
        
        # Memoria RAM
        mem_info = self.adb("shell cat /proc/meminfo")
        mem_free = "N/D"
        mem_total = "N/D"
        for line in mem_info.splitlines():
            if "MemTotal" in line:
                mem_total = line.split(":")[1].strip()
            elif "MemAvailable" in line:
                mem_free = line.split(":")[1].strip()

        # Espacio en disco
        df = self.adb("shell df -h /data")
        storage_info = "N/D"
        df_lines = df.splitlines()
        if len(df_lines) > 1:
            storage_info = " ".join(df_lines[1].split()[1:4])  # Total Used Avail

        return {
            "model": model,
            "android_version": android_ver,
            "uptime": uptime,
            "ram_total": mem_total,
            "ram_available": mem_free,
            "storage_data": storage_info,
            "channel": self.get_current_channel()
        }

    # --- OPTIMIZACIÓN Y MANTENIMIENTO ---
    def clean_ram(self) -> str:
        """Cierra apps secundarias en segundo plano para acelerar la TV."""
        self.adb("shell am kill-all")
        self.adb("shell sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null")
        return "Memoria RAM optimizada y procesos en segundo plano limpiados."

    # --- TEMPORIZADOR DE APAGADO INTELIGENTE (SLEEP TIMER) ---
    def start_sleep_timer(self, minutes: int, gradual: bool = True):
        self.cancel_sleep = False
        def _sleep_worker():
            total_seconds = minutes * 60
            paso = total_seconds / 5 if gradual else total_seconds
            for i in range(5 if gradual else 1):
                if self.cancel_sleep:
                    return
                time.sleep(paso)
                if gradual and i < 4:
                    self.volume_down()
            if not self.cancel_sleep:
                self.key_power() # Apagar la tele

        self.sleep_timer_thread = threading.Thread(target=_sleep_worker, daemon=True)
        self.sleep_timer_thread.start()
        return f"Temporizador de apagado activado: {minutes} minutos."

    def cancel_sleep_timer(self):
        self.cancel_sleep = True
        return "Temporizador de apagado cancelado."
