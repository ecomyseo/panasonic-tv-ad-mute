"""
Lo que el servicio hace solo, con la lógica separada de la TV para poder probarla con un reloj de mentira:

- VolumenCanales: recuerda el volumen al que dejas cada canal y lo pone al volver; modo noche con tope.
- Despertador: a la hora y los días elegidos, enciende la tele en un canal y con un volumen.
- Salida: si el móvil no está en la WiFi de casa un rato y la tele sigue encendida, avisa y la apaga.
"""

import json
import os
import time

import ajustes
import estado

ESTABLE = 8         # segundos sin tocar el volumen para darlo por bueno
TRAS_CAMBIO = 10    # segundos en un canal antes de aprender su volumen (al zapear no cuenta)
AVISO_SALIDA = 60   # segundos entre «apago la tele en 1 minuto» y apagarla


def minuto_del_dia(t=None) -> int:
    lt = time.localtime(t if t is not None else time.time())
    return lt.tm_hour * 60 + lt.tm_min


def tope_noche(a: dict, t=None):
    """El tope de volumen si ahora es «noche» y el modo está activo; None si no."""
    if not a.get("noche_activo"):
        return None
    if ajustes.en_franja(minuto_del_dia(t), a["noche_desde"], a["noche_hasta"]):
        return int(a["noche_tope"])
    return None


class VolumenCanales:
    FICHERO = "volumen_canales.json"

    def __init__(self, reloj=time.time, estable=ESTABLE, tras_cambio=TRAS_CAMBIO):
        self.reloj = reloj
        self.estable = estable
        self.tras_cambio = tras_cambio
        self.canal = None
        self.desde = 0.0
        self.ultimo = None
        self.ultimo_desde = 0.0
        self.pendiente = None   # volumen que el hub va a poner: mientras tanto no se aprende nada
        self.preferidos = self._cargar()

    def _cargar(self) -> dict:
        try:
            with open(estado.ruta(self.FICHERO), encoding="utf-8") as f:
                datos = json.load(f)
            return {str(k): int(v) for k, v in datos.items()} if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            return {}

    def _guardar(self):
        ruta = estado.ruta(self.FICHERO)
        try:
            with open(ruta + ".tmp", "w", encoding="utf-8") as f:
                json.dump(self.preferidos, f, ensure_ascii=False)
            os.replace(ruta + ".tmp", ruta)
        except OSError:
            pass

    def cambio_canal(self, canal, tope=None):
        """Al cambiar de canal: el volumen que hay que poner (el de ese canal, sin pasar del tope) o None."""
        self.canal = canal
        self.desde = self.reloj()
        self.ultimo = None
        objetivo = self.preferidos.get(canal)
        if objetivo is not None and tope is not None:
            objetivo = min(objetivo, tope)
        self.pendiente = objetivo
        return objetivo

    def observar(self, volumen, silenciada=False):
        """Lectura periódica del volumen. Si lleva quieto un rato en este canal, se apunta como el suyo."""
        ahora = self.reloj()
        if self.pendiente is not None:
            return None
        if volumen != self.ultimo:
            self.ultimo, self.ultimo_desde = volumen, ahora
            return None
        if (self.canal is None or silenciada or ahora - self.desde < self.tras_cambio
                or ahora - self.ultimo_desde < self.estable or self.preferidos.get(self.canal) == volumen):
            return None
        self.preferidos[self.canal] = volumen
        self._guardar()
        return volumen

    def puesto_por_el_hub(self, volumen):
        """El hub ha cambiado el volumen: no es una preferencia nueva del usuario (cuenta como ya estable)."""
        self.ultimo, self.ultimo_desde = volumen, self.reloj() - self.estable
        self.pendiente = None


class ContadorNegros:
    """
    Fotogramas negros por minuto y canal. La tele escribe el brillo medio de la imagen unas 8 veces por segundo
    (MtkTvAvMode_jni: ui2_avg_pixel_luma); entre anuncio y anuncio suele haber un instante en negro. Se apunta cuántas
    veces se entra en negro cada minuto para compararlo con tus «Silenciar» y ver si sirve para detectar los cortes.
    """

    UMBRAL = 4

    def __init__(self, reloj=time.time):
        self.reloj = reloj
        self.minuto, self.canal, self.negros, self.muestras, self.ultimo = "", "", 0, 0, 255

    def muestra(self, valor: int, canal: str):
        """Devuelve el minuto que se acaba de cerrar ({minuto, canal, negros, muestras}) o None."""
        minuto = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.reloj()))
        cerrado = None
        if minuto != self.minuto or canal != self.canal:
            if self.minuto and self.muestras:
                cerrado = {"minuto": self.minuto, "canal": self.canal, "negros": self.negros, "muestras": self.muestras}
            self.minuto, self.canal, self.negros, self.muestras = minuto, canal, 0, 0
        self.muestras += 1
        if valor <= self.UMBRAL < self.ultimo:
            self.negros += 1
        self.ultimo = valor
        return cerrado


class Despertador:
    def __init__(self):
        self.hecho = ""   # día (AAAA-MM-DD) en que ya ha sonado

    def toca(self, a: dict, t=None) -> bool:
        if not a.get("despertador_activo"):
            return False
        t = t if t is not None else time.time()
        lt = time.localtime(t)
        dia = time.strftime("%Y-%m-%d", lt)
        if self.hecho == dia or str(lt.tm_wday + 1) not in a["despertador_dias"]:
            return False
        h, m = int(a["despertador_hora"][:2]), int(a["despertador_hora"][3:])
        ahora = lt.tm_hour * 60 + lt.tm_min
        if h * 60 + m <= ahora < h * 60 + m + 5:  # cinco minutos de margen por si el servicio iba tarde
            self.hecho = dia
            return True
        return False


class Salida:
    """
    El móvil en la WiFi = estás en casa. Si no se le ve en `salir_minutos` y la tele está encendida, primero se avisa
    en la pantalla y, si en un minuto nadie toca el volumen ni cambia de canal, se apaga.
    """

    def __init__(self, reloj=time.time):
        self.reloj = reloj
        self.visto = reloj()
        self.avisado = 0.0
        self.huella = None   # (volumen, canal) al avisar: si cambia, hay alguien

    def observar(self, a: dict, presente: bool, encendida, huella):
        """Devuelve 'avisar', 'apagar' o None."""
        ahora = self.reloj()
        if not a.get("salir_activo") or not a.get("salir_ip"):
            self.visto, self.avisado = ahora, 0.0
            return None
        if presente or encendida is not True:
            self.visto, self.avisado = ahora, 0.0
            return None
        if self.avisado:
            if huella != self.huella:  # alguien ha tocado algo: está en casa
                self.visto, self.avisado = ahora, 0.0
                return None
            if ahora - self.avisado >= AVISO_SALIDA:
                self.visto, self.avisado = ahora, 0.0
                return "apagar"
            return None
        if ahora - self.visto >= int(a["salir_minutos"]) * 60:
            self.avisado, self.huella = ahora, huella
            return "avisar"
        return None
