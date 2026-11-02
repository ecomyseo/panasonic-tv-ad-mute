"""
La señal de la guía (EIT «ahora / a continuación») como pista de los anuncios.

Medido en la TV el 2026-11-02: con Antena 3 puesta, la cadena reenvió el «ahora» del canal (mismo programa, otro
identificador) siete veces entre las 12:44 y las 12:53, y ninguna en la media hora anterior. Puede ser el corte de
publicidad, pero NO está confirmado. Por eso, de fábrica, el hub solo la APUNTA junto a lo que haces tú (pulsar
«Silenciar», devolver el sonido) y el mando web enseña cuántas veces han coincidido. Silencia con ella solo si se
activa a mano (botón del mando o GUIA_SILENCIA=1).

La TV lo escribe en el logcat (etiqueta MtkTvEvent_jni) una vez por cada proceso que escucha:
    _event_nfy_fct callback_type=4, pv_tag=0x457, arg=0xc0081,0x1,0x0,0x0
arg[0] es el identificador del canal en hexadecimal (0xc0081 = 786561, Antena 3) y arg[1] si es el «ahora» (0) o
el «a continuación» (1). Al cambiar de canal la TV también lo pide: eso no cuenta.
"""

import json
import os
import re
import time

import estado

_RE = re.compile(r"_event_nfy_fct callback_type=4, pv_tag=0x[0-9a-fA-F]+, arg=0x([0-9a-fA-F]+),0x[01]\b")
REPETIDA = 5         # la misma novedad llega a varios procesos y en dos partes (ahora y a continuación)
VENTANA_BOTON = 120  # una señal y un «Silenciar» separados como mucho esto cuentan como la misma cosa
FICHERO = "senales_guia.jsonl"
MAX_BYTES = 512 * 1024


class SenalGuia:
    def __init__(self, tras_zapeo=20, calma=480, reloj=time.time):
        self.tras_zapeo = tras_zapeo
        self.calma = calma
        self.reloj = reloj
        self.canal_id = None
        self.desde = 0.0
        self.ultima = 0.0

    def cambio_canal(self, canal_id):
        self.canal_id = str(canal_id)
        self.desde = self.reloj()
        self.ultima = 0.0  # recién llegado no se sabe: se da por tranquila

    def procesar(self, linea):
        """None si la línea no es una novedad de la guía del canal que se ve; si lo es, 'inicio' cuando llega
        tras un rato de calma (posible principio de un corte) o 'sigue' cuando llega dentro de una racha."""
        m = _RE.search(linea)
        if not m or self.canal_id is None:
            return None
        if str(int(m.group(1), 16)) != self.canal_id:
            return None
        ahora = self.reloj()
        if ahora - self.desde < self.tras_zapeo or ahora - self.ultima < REPETIDA:
            return None
        tipo = "inicio" if ahora - self.ultima >= self.calma else "sigue"
        self.ultima = ahora
        return tipo


# ----------------------------------------------------------------- registro: señales y lo que hace el usuario
def apuntar(tipo, canal, momento=None):
    """tipo: 'inicio' / 'sigue' (señal de la guía), 'boton' (Silenciar a mano), 'fin' (devolver el sonido a mano)."""
    ruta = estado.ruta(FICHERO)
    try:
        if os.path.exists(ruta) and os.path.getsize(ruta) > MAX_BYTES:
            os.replace(ruta, ruta + ".1")
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(momento or time.time(), 1), "tipo": tipo, "canal": canal or ""},
                               ensure_ascii=False) + "\n")
    except OSError:
        pass


def leer(desde=0.0):
    filas = []
    for nombre in (FICHERO + ".1", FICHERO):
        try:
            with open(estado.ruta(nombre), encoding="utf-8") as f:
                for linea in f:
                    try:
                        fila = json.loads(linea)
                    except ValueError:
                        continue
                    if isinstance(fila, dict) and float(fila.get("t") or 0) >= desde:
                        filas.append(fila)
        except OSError:
            continue
    filas.sort(key=lambda f: f["t"])
    return filas


def resumen(dias=7, ultimas=8, ahora=None):
    """Cuántas veces ha saltado la señal, cuántas has pulsado «Silenciar» y cuántas han coincidido."""
    ahora = ahora or time.time()
    filas = leer(ahora - dias * 86400)
    senales = [f for f in filas if f["tipo"] == "inicio"]
    botones = [f for f in filas if f["tipo"] == "boton"]

    def cerca(a, lista):
        return any(b["canal"] == a["canal"] and abs(b["t"] - a["t"]) <= VENTANA_BOTON for b in lista)

    lista = [{"hora": time.strftime("%d/%m %H:%M", time.localtime(s["t"])), "canal": s["canal"],
              "con_boton": cerca(s, botones)} for s in senales[-ultimas:]]
    lista.reverse()
    return {"senales": len(senales), "botones": len(botones),
            "coinciden": sum(1 for b in botones if cerca(b, senales)), "ultimas": lista}
