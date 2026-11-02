"""
Panasonic Google TV ADB Core Manager
Controlador completo para televisores Panasonic con Android TV / Google TV.

Modelo detectado: Panasonic Google TV LCD
Product:         OZUM_Panasonic
Device codename: kowloon (MediaTek MT5895)
Plataforma:      Android 14

Todas las órdenes van a ADB como lista de argumentos (sin shell en el equipo local).
Lo que viaja al shell de la TV y lleva datos de fuera se entrecomilla con shlex.quote.
"""

import re
import shlex
import socket
import subprocess
import threading
import time

import config

# Datos exactos del televisor detectado por ADB
TV_MODEL_INFO = {
    "product": "OZUM_Panasonic",
    "model": "Panasonic_Google_TV_LCD",
    "codename": "kowloon",
    "soc": "MediaTek MT5895",
    "android": "14"
}

KEY_MUTE = 164
KEY_VOL_UP = 24
KEY_VOL_DOWN = 25
KEY_POWER = 26
KEY_SLEEP = 223
KEY_WAKEUP = 224
KEY_HOME = 3
KEY_BACK = 4
KEY_CH_UP = 166
KEY_CH_DOWN = 167
KEY_GUIDE = 172
KEY_LAST_CHANNEL = 229  # vuelve al canal anterior (comprobado en la Panasonic OZUM el 2026-11-02)

APPS_CONOCIDAS = {
    "YouTube": "com.google.android.youtube.tv/com.google.android.apps.youtube.tv.activity.ShellActivity",
    "YouTube Music": "com.google.android.youtube.tvmusic",
    "Netflix": "com.netflix.ninja/.MainActivity",
    "Movistar+": "com.movistarplus.androidtv",
    "Atresplayer": "com.antena3.atresplayer.tv",
    "RTVE Play": "com.rtve.androidtv",
    "Tivify": "com.tvup.tivify.app.tv",
    "TDT Live TV": "com.mediatek.wwtv.tvcenter/.nav.TurnkeyUiMainActivity"
}

PAQUETE_TDT = "com.mediatek.wwtv.tvcenter"

# En Windows, el servicio en segundo plano no tiene consola: sin esto, cada orden a adb abriría una ventana
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

NAVEGADORES_TV = ["com.vewd.core.browser", "com.android.chrome", "org.mozilla.tv.firefox"]

_PAQUETE_VALIDO = re.compile(r"^[A-Za-z0-9_.]+(/[A-Za-z0-9_.$]+)?$")


class PanasonicTVManager:
    def __init__(self, tv_ip=None):
        self.cfg = config.cargar()
        self.tv_ip = config.normalizar_ip(tv_ip or self.cfg["TV_IP"])
        self.tv_mac = (self.cfg.get("TV_MAC") or "").strip()
        self.adb_base = config.adb_bin(self.cfg)
        self.model_info = TV_MODEL_INFO
        self.is_muted = False
        self.silenciada_por_nosotros = False
        self.lectura_mute_fiable = False
        self.fin_silencio = 0.0
        self._temporizador = None
        self._lock = threading.RLock()
        self._sleep_evento = threading.Event()
        self.sleep_timer_thread = None
        self._cache_paquetes = (0.0, None)

    # ------------------------------------------------------------------ ADB
    def _ejecutar(self, args, timeout=6):
        try:
            # stdin=DEVNULL: en Windows, si otro hilo está esperando una tecla en la consola (el menú),
            # heredar esa entrada deja colgado el arranque de adb para siempre
            res = subprocess.run(self.adb_base + list(args), capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                 encoding="utf-8", errors="replace", timeout=timeout, creationflags=SIN_VENTANA)
            return res.returncode, (res.stdout or "").strip(), (res.stderr or "").strip()
        except FileNotFoundError:
            return 127, "", "ADB no está instalado"
        except subprocess.TimeoutExpired:
            return 124, "", "Tiempo agotado hablando con la TV"
        except OSError as e:
            return 1, "", str(e)

    def adb_args(self, *args, timeout=6) -> str:
        _, out, _ = self._ejecutar(["-s", self.tv_ip] + list(args), timeout=timeout)
        return out

    def shell(self, *partes, timeout=6) -> str:
        return self.adb_args("shell", *partes, timeout=timeout)

    def adb(self, cmd: str, timeout=5) -> str:
        """Compatibilidad: 'shell input keyevent 3' -> lista de argumentos, sin shell local."""
        return self.adb_args(*shlex.split(cmd), timeout=timeout)

    def tecla(self, codigo: int) -> None:
        self.shell("input", "keyevent", str(int(codigo)))

    def connect(self) -> bool:
        """Asegura la conexión con la TV por ADB."""
        _, out, err = self._ejecutar(["connect", self.tv_ip], timeout=8)
        texto = (out + " " + err).lower()
        ok = ("connected to" in texto or "already connected" in texto) and "fail" not in texto and "unable" not in texto
        if ok:
            model = self.shell("getprop", "ro.product.model")
            if model and "panasonic" not in model.lower():
                print(f"[Aviso] Modelo detectado: {model} (puede no ser la Panasonic esperada)")
        return ok

    def estado_conexion(self) -> str:
        """'device' (conectada), 'unauthorized' (falta aceptar en la TV), 'offline' o 'sin_conexion'."""
        _, out, _ = self._ejecutar(["devices"], timeout=5)
        for linea in out.splitlines():
            partes = linea.split()
            if len(partes) >= 2 and partes[0] == self.tv_ip:
                return partes[1]
        return "sin_conexion"

    # ------------------------------------------------------------ SONIDO
    def estado_mute(self):
        """True / False según AudioService de Android; None si no se puede leer."""
        out = self.shell("dumpsys audio | grep -A4 -e '- STREAM_MUSIC:'", timeout=8)
        en_bloque = False
        for linea in out.splitlines():
            l = linea.strip()
            if l.startswith("- STREAM_"):
                en_bloque = l.startswith("- STREAM_MUSIC")
                continue
            if en_bloque and l.lower().startswith("muted:"):
                return l.split(":", 1)[1].strip().lower() == "true"
        return None

    def silenciar(self) -> bool:
        """Silencia si no lo estaba. Devuelve True solo si la hemos silenciado nosotros."""
        with self._lock:
            if self.silenciada_por_nosotros:
                return False
            antes = self.estado_mute()
            if antes is True:
                return False  # ya estaba silenciada por el usuario: no se toca
            self.tecla(KEY_MUTE)
            time.sleep(0.6)
            despues = self.estado_mute()
            # Solo nos fiamos de la lectura si ha cambiado al pulsar Mute
            self.lectura_mute_fiable = (antes is False and despues is True)
            self.silenciada_por_nosotros = True
            self.is_muted = True
            return True

    def restaurar(self) -> bool:
        """Devuelve el sonido solo si lo quitamos nosotros y el usuario no lo ha devuelto ya."""
        with self._lock:
            self._cancelar_temporizador()
            if not self.silenciada_por_nosotros:
                return False
            self.silenciada_por_nosotros = False
            self.is_muted = False
            self.fin_silencio = 0.0
            if self.lectura_mute_fiable and self.estado_mute() is False:
                return False  # el usuario ya lo devolvió con el mando
            self.tecla(KEY_MUTE)
            return True

    def silenciar_temporal(self, segundos: int, al_terminar=None) -> bool:
        """Silencia durante N segundos y luego devuelve el sonido (temporizador = vigilante)."""
        with self._lock:
            if not self.silenciar():
                return False
            self.fin_silencio = time.time() + segundos

            def _fin():
                restaurado = self.restaurar()
                if al_terminar:
                    try:
                        al_terminar(restaurado)
                    except Exception as e:  # noqa: BLE001
                        print(f"[Aviso] al_terminar: {e}")

            t = threading.Timer(segundos, _fin)
            t.daemon = True
            t.start()
            self._temporizador = t
            return True

    def _cancelar_temporizador(self):
        if self._temporizador is not None:
            self._temporizador.cancel()
            self._temporizador = None

    def toggle_mute(self) -> str:
        """Mute manual (como el botón del mando)."""
        with self._lock:
            self.tecla(KEY_MUTE)
            if self.silenciada_por_nosotros:
                # El usuario devuelve el sonido a mano: dejamos de vigilarlo
                self._cancelar_temporizador()
                self.silenciada_por_nosotros = False
                self.is_muted = False
                self.fin_silencio = 0.0
            else:
                self.is_muted = not self.is_muted
        return "Silencio alternado"

    def volume_up(self) -> str:
        self.tecla(KEY_VOL_UP)
        return "Volumen +"

    def volume_down(self) -> str:
        self.tecla(KEY_VOL_DOWN)
        return "Volumen -"

    # ---------------------------------------------------- ENCENDIDO / APAGADO
    def esta_encendida(self):
        out = self.shell("dumpsys power | grep -m1 mWakefulness=", timeout=6)
        if "Awake" in out:
            return True
        if "Asleep" in out or "Dozing" in out:
            return False
        return None

    def encender(self) -> str:
        if self.tv_mac:
            enviar_wol(self.tv_mac)
            time.sleep(2)
        self.connect()
        self.tecla(KEY_WAKEUP)
        return "Orden de encendido enviada" + (" (Wake-on-LAN + ADB)" if self.tv_mac else "")

    def apagar(self) -> str:
        self.tecla(KEY_SLEEP)
        return "TV apagada (standby)"

    def key_power(self) -> str:
        self.tecla(KEY_POWER)
        return "Encendido / Apagado (Standby)"

    # ------------------------------------------------------------ MANDO
    def key_home(self) -> str:
        self.tecla(KEY_HOME)
        return "Inicio (Home)"

    def key_back(self) -> str:
        self.tecla(KEY_BACK)
        return "Volver (Back)"

    def canal_mas(self) -> str:
        self.tecla(KEY_CH_UP)
        return "Canal +"

    def canal_menos(self) -> str:
        self.tecla(KEY_CH_DOWN)
        return "Canal -"

    def ir_a_numero(self, numero) -> bool:
        """Sintoniza un canal tecleando su número (las cifras van en una sola orden, como en el mando)."""
        texto = str(numero).strip()
        if not texto.isdigit() or len(texto) > 4:
            return False
        self.shell("input", "keyevent", *[str(7 + int(c)) for c in texto])
        return True

    def poner_canal(self, numero, esperar=time.sleep) -> bool:
        """Pone un canal de la TDT por su número. Si delante hay otra app, abre antes la TDT."""
        if not str(numero).strip().isdigit():
            return False
        if not self.viendo_tdt():
            self.launch_app("TDT Live TV")  # en otra app, las cifras irían a esa app
            esperar(4)
        return self.ir_a_numero(numero)

    def canal_anterior(self) -> str:
        self.tecla(KEY_LAST_CHANNEL)
        return "Canal anterior"

    def guia(self) -> str:
        self.tecla(KEY_GUIDE)
        return "Guía de la TV"

    def key_dpad(self, direction: str) -> str:
        mapping = {"up": 19, "down": 20, "left": 21, "right": 22, "enter": 66, "ok": 66}
        direccion = (direction or "").lower()
        self.tecla(mapping.get(direccion, 66))
        return f"Tecla {direccion.upper()} enviada"

    def send_text(self, text: str) -> str:
        """Escribe texto en el campo activo de la TV (solo caracteres del teclado inglés)."""
        texto = (text or "").replace("%", "").replace(" ", "%s")[:200]
        if not texto:
            return "Texto vacío"
        self.shell("input", "text", shlex.quote(texto))
        return f"Texto enviado: {text}"

    # ------------------------------------------------------------ APPS
    def get_known_apps(self) -> dict:
        return dict(APPS_CONOCIDAS)

    def paquetes_instalados(self, forzar=False):
        """Lista de paquetes de la TV (caché 10 min). None si no se puede leer."""
        momento, lista = self._cache_paquetes
        if not forzar and lista is not None and time.time() - momento < 600:
            return lista
        out = self.shell("pm", "list", "packages", timeout=10)
        paquetes = [l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("package:")]
        if not paquetes:
            return None
        self._cache_paquetes = (time.time(), paquetes)
        return paquetes

    def apps_instaladas(self) -> list:
        instalados = self.paquetes_instalados()
        if instalados is None:
            return list(APPS_CONOCIDAS.keys())
        return [nombre for nombre, destino in APPS_CONOCIDAS.items() if destino.split("/")[0] in instalados]

    def launch_app(self, package_or_alias: str) -> str:
        target = APPS_CONOCIDAS.get(package_or_alias, package_or_alias)
        if not _PAQUETE_VALIDO.match(target or ""):
            return "Aplicación no válida"
        if "/" in target:
            self.shell("am", "start", "-n", target)
        else:
            out = self.shell("monkey", "-p", target, "-c", "android.intent.category.LEANBACK_LAUNCHER", "1", timeout=10)
            if "No activities found" in out or "Error" in out:
                self.shell("monkey", "-p", target, "-c", "android.intent.category.LAUNCHER", "1", timeout=10)
        return f"Lanzando {package_or_alias}..."

    # ------------------------------------------- INFORMACIÓN EN TIEMPO REAL
    @staticmethod
    def extraer_canal(linea: str):
        """Saca el canal de una línea de MtkTvChannelList_jni ('Current channel ... name--X...')."""
        if "Current channel" not in linea or "name--" not in linea:
            return None
        try:
            canal = linea.split("name--", 1)[1].split("...")[0].strip()
            cid = linea.split("channelId--", 1)[1].split(",")[0].strip() if "channelId--" in linea else "?"
            rec = linea.split("svlRecId--", 1)[1].split(",")[0].strip() if "svlRecId--" in linea else "?"
            return {"name": canal, "channel_id": cid, "svl_rec_id": rec} if canal else None
        except IndexError:
            return None

    @staticmethod
    def extraer_rotulo(linea: str):
        """Rótulo que enseña la TV al cambiar de canal: ('numero', '3') o ('nombre', 'Antena 3')."""
        if "MtkTvBannerBase" not in linea:
            return None
        for clave, tipo in (("getChannelNumber=", "numero"), ("getChannelName=", "nombre")):
            if clave in linea:
                valor = linea.split(clave, 1)[1].strip()
                return (tipo, valor) if valor else None
        return None

    def get_current_channel(self) -> dict:
        """
        Canal actual leyendo el logcat de MtkTvChannelList_jni.
        Método confirmado en Panasonic OZUM / kowloon / Android 14.
        """
        for args, tiempo in ((("logcat", "-d", "-t", "80", "-s", "MtkTvChannelList_jni:D"), 6),
                             (("logcat", "-d", "-t", "300"), 8)):
            out = self.adb_args(*args, timeout=tiempo)
            for linea in reversed(out.splitlines()):
                canal = self.extraer_canal(linea)
                if canal:
                    return canal
        return {"name": "TDT / Desconocido", "channel_id": "?", "svl_rec_id": "?"}

    def get_current_program(self) -> dict:
        """Programa en emisión en el canal actual, según la guía EPG descargada."""
        from epg import GuiaEPG
        canal = self.get_current_channel().get("name", "")
        return GuiaEPG().ahora(canal)

    def get_tv_stats(self) -> dict:
        mem_total = mem_free = "N/D"
        for linea in self.shell("cat", "/proc/meminfo").splitlines():
            if linea.startswith("MemTotal"):
                mem_total = linea.split(":")[1].strip()
            elif linea.startswith("MemAvailable"):
                mem_free = linea.split(":")[1].strip()
        df_lines = self.shell("df", "-h", "/data").splitlines()
        storage_info = " ".join(df_lines[1].split()[1:4]) if len(df_lines) > 1 else "N/D"
        canal_info = self.get_current_channel()
        return {
            "model": self.shell("getprop", "ro.product.model"),
            "android_version": self.shell("getprop", "ro.build.version.release"),
            "uptime": self.shell("uptime"),
            "ram_total": mem_total,
            "ram_available": mem_free,
            "storage_data": storage_info,
            "channel": canal_info.get("name", "?"),
            "channel_id": canal_info.get("channel_id", "?"),
        }

    # ----------------------------------------------------- MANTENIMIENTO
    def clean_ram(self) -> str:
        """Cierra apps en segundo plano para aligerar la TV."""
        self.shell("am", "kill-all")
        return "Procesos en segundo plano de la TV cerrados."

    # ------------------------------------------- TEMPORIZADOR DE APAGADO
    def start_sleep_timer(self, minutes, gradual: bool = True) -> str:
        self.cancel_sleep_timer()
        evento = threading.Event()
        self._sleep_evento = evento
        total = float(minutes) * 60

        def _sleep_worker():
            pasos = 5 if gradual else 1
            for i in range(pasos):
                if evento.wait(total / pasos):
                    return
                if gradual and i < pasos - 1:
                    self.volume_down()
            if not evento.is_set():
                self.apagar()

        self.sleep_timer_thread = threading.Thread(target=_sleep_worker, daemon=True)
        self.sleep_timer_thread.start()
        return f"Temporizador de apagado activado: {minutes} minutos."

    def cancel_sleep_timer(self) -> str:
        self._sleep_evento.set()
        return "Temporizador de apagado cancelado."

    # ------------------------------------- BANNER Y AVISOS EN LA PANTALLA
    def _foco_actual(self) -> str:
        return self.shell("dumpsys window | grep -m1 mCurrentFocus", timeout=6)

    def viendo_tdt(self) -> bool:
        """¿Está delante la app de la TDT? (si no, teclear un número escribiría en otra app)."""
        return PAQUETE_TDT in self._foco_actual()

    def show_banner_on_tv(self, server_ip="192.168.1.50", port=8080, title=None, duration=8) -> str:
        """Abre el banner con la ficha en el navegador de la TV y lo cierra solo."""
        import urllib.parse
        param = f"?title={urllib.parse.quote(title)}" if title else ""
        url = f"http://{server_ip}:{port}/tv_banner{param}"
        instalados = self.paquetes_instalados() or []
        navegador = next((p for p in NAVEGADORES_TV if p in instalados), None)
        if navegador == "com.vewd.core.browser":
            self.shell("am", "start", "-n", "com.vewd.core.browser/.BrowserActivity", "-d", shlex.quote(url))
        else:
            self.shell("am", "start", "-a", "android.intent.action.VIEW", "-d", shlex.quote(url))

        def _auto_close():
            time.sleep(duration)
            foco = self._foco_actual().lower()
            # Solo se pulsa Volver si el navegador sigue delante (si no, sacaría al usuario de su app)
            if any(p in foco for p in NAVEGADORES_TV) or "browser" in foco:
                self.key_back()

        threading.Thread(target=_auto_close, daemon=True).start()
        aviso = "" if navegador else " (sin navegador conocido: se ha usado el predeterminado)"
        return f"Banner proyectado en la TV por {duration} segundos{aviso}."

    def post_tv_notification(self, title: str, text: str) -> str:
        """Muestra una notificación en la TV."""
        self.shell("cmd", "notification", "post", "-S", "bigtext", "-t", shlex.quote(title[:80]),
                   "tv_hub", shlex.quote(text[:300]))
        return "Notificación enviada a la pantalla de la TV."


def enviar_wol(mac: str) -> bool:
    """Paquete mágico Wake-on-LAN a la MAC de la TV (si la TV tiene 'encender por red')."""
    limpio = re.sub(r"[^0-9A-Fa-f]", "", mac or "")
    if len(limpio) != 12:
        return False
    paquete = bytes.fromhex("FF" * 6 + limpio * 16)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(paquete, ("255.255.255.255", 9))
        return True
    except OSError:
        return False
    finally:
        s.close()
