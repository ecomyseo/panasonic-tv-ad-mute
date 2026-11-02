"""
Avisos en la pantalla de la TV, encima de lo que se esté viendo, en el CENTRO y con letra grande.

Los pinta «TV Hub Avisos» (avisos_app/TVHubAvisos.apk): una app propia de 17 KB, sin icono ni pantalla, que solo
obedece al ADB. El hub le manda cada aviso con «am broadcast» y ella lo enseña unos segundos sin quitarle el mando
a la tele. «Preparar avisos» la instala y le da el permiso de «mostrar encima de otras apps»; se quita como
cualquier otra app. No se toca nada del sistema de la TV.

Si no está y la TV tiene TvOverlay (la app de la tienda que se usaba antes), el aviso sale con ella: en una esquina
y con su letra, que no se puede cambiar.
"""

import json
import os
import re
import shlex
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

import config

PAQUETE = "es.gmartos.tvhub.avisos"
RECEPTOR = PAQUETE + "/.Receptor"
ACCION = "es.gmartos.tvhub.AVISO"
POSICIONES = ("centro", "arriba", "abajo")
PAQUETE_TVOVERLAY = "com.tabdeveloper.tvoverlay"
PUERTO = 5001  # el de TvOverlay


def ruta_apk() -> str:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "avisos_app", "TVHubAvisos.apk")


def _una_linea(texto) -> str:
    return " ".join(str(texto or "").split())


class AvisosTV:
    def __init__(self, tv, cfg=None):
        cfg = cfg or config.cargar()
        self.tv = tv
        self.activo = str(cfg.get("AVISOS_EN_TV", "1")).strip() == "1"
        url = str(cfg.get("TVOVERLAY_URL") or "").strip().rstrip("/")
        if not url:
            url = f"http://{(tv.tv_ip or '').split(':')[0]}:{PUERTO}"
        self.url = url
        self.duracion = config.entero(cfg, "AVISOS_DURACION", 8)
        self.tamano = min(max(config.entero(cfg, "AVISOS_TAMANO", 40), 18), 96)
        posicion = str(cfg.get("AVISOS_POSICION") or "").strip().lower()
        self.posicion = posicion if posicion in POSICIONES else "centro"

    # ------------------------------------------------------------ estado
    def modo(self, forzar=False) -> str:
        """'app' (la propia: centrada y grande), 'tvoverlay' (en una esquina) o '' (ninguna lista)."""
        if not self.activo:
            return ""
        paquetes = self.tv.paquetes_instalados(forzar=forzar)
        if paquetes and PAQUETE in paquetes:
            return "app"
        return "tvoverlay" if self._tvoverlay_escucha() else ""

    def responde(self) -> bool:
        return bool(self.modo())

    def _tvoverlay_escucha(self) -> bool:
        partes = urllib.parse.urlparse(self.url)
        try:
            with socket.create_connection((partes.hostname, partes.port or 80), timeout=1):
                return True
        except (OSError, ValueError):
            return False

    # ------------------------------------------------------------ enseñar
    def mostrar(self, titulo, mensaje="", duracion=None, detalle="", imagen="", solo_app=False) -> bool:
        """Primero la app propia (una orden ADB); si no está o no puede, TvOverlay (salvo con solo_app)."""
        if not self.activo:
            return False
        segundos = int(duracion or self.duracion)
        if self._mostrar_app(titulo, mensaje, segundos, detalle=detalle, imagen=imagen):
            return True
        if solo_app:
            return False
        texto = " · ".join(t for t in (_una_linea(detalle), _una_linea(mensaje)) if t)
        return self._mostrar_tvoverlay(titulo, texto, segundos)

    def _mostrar_app(self, titulo, mensaje, segundos, detalle="", imagen="") -> bool:
        orden = ["am", "broadcast", "-f", "32", "-n", RECEPTOR, "-a", ACCION,
                 "--ei", "segundos", str(int(segundos)), "--ei", "tamano", str(self.tamano),
                 "--es", "posicion", self.posicion]
        for clave, valor in (("titulo", titulo), ("detalle", detalle), ("mensaje", mensaje), ("imagen", imagen)):
            valor = _una_linea(valor)
            if valor:
                orden += ["--es", clave, shlex.quote(valor)]
        for intento in range(2):
            m = re.search(r"result=(-?\d+)", self.tv.shell(*orden, timeout=10) or "")
            codigo = m.group(1) if m else ""
            if codigo == "1":
                return True
            if codigo == "2" and intento == 0:
                # Le han quitado el permiso de pintar encima (o es la primera vez): se le vuelve a dar
                self.tv.shell("appops", "set", PAQUETE, "SYSTEM_ALERT_WINDOW", "allow")
                continue
            return False
        return False

    def _mostrar_tvoverlay(self, titulo, mensaje, segundos) -> bool:
        cuerpo = {"title": str(titulo)[:80], "message": str(mensaje)[:200], "source": "Panasonic TV Hub",
                  "smallIcon": "mdi:television", "duration": int(segundos)}
        peticion = urllib.request.Request(self.url + "/notify", method="POST",
                                          data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
                                          headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=3) as r:
                return 200 <= r.status < 300
        except (urllib.error.URLError, OSError, ValueError):
            return False

    # ------------------------------------------------------------ instalar
    def instalada(self, forzar=False):
        """True / False, o None si la TV no contesta."""
        paquetes = self.tv.paquetes_instalados(forzar=forzar)
        return None if paquetes is None else PAQUETE in paquetes

    def preparar(self):
        """
        Instala la app de avisos si falta, le da permiso para pintar encima y enseña un aviso de prueba.
        Devuelve (correcto, mensaje).
        """
        if not self.activo:
            return False, "Los avisos en la TV están desactivados (AVISOS_EN_TV=0)"
        instalada = self.instalada(forzar=True)
        if instalada is None:
            return False, "La TV no responde"
        if not instalada:
            apk = ruta_apk()
            if not os.path.exists(apk):
                return False, f"Falta la app de avisos ({apk})"
            _, salida, error = self.tv._ejecutar(["-s", self.tv.tv_ip, "install", "-r", apk], timeout=180)
            if "Success" not in salida:
                detalle = (error or salida).strip().splitlines()
                return False, "La TV no ha aceptado la app de avisos" + (f": {detalle[-1]}" if detalle else "")
            self.tv.paquetes_instalados(forzar=True)
        self.tv.shell("appops", "set", PAQUETE, "SYSTEM_ALERT_WINDOW", "allow")
        if self._mostrar_app("Panasonic TV Hub", "Los avisos saldrán así: en el centro y con letra grande.", 8):
            return True, "Avisos listos: mira la tele"
        return False, "La app de avisos está instalada, pero la TV no ha enseñado el aviso"
