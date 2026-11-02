"""
Estado compartido entre el silenciador automático (demonio), el mando web y el menú.

- estado.json: lo escribe SOLO el demonio (latido, canal, silencio, estadísticas).
- pausa:       si existe, el silenciador automático no actúa.
- orden_*:     órdenes de un solo uso que el demonio recoge (silenciar, restaurar).
"""

import json
import os
import tempfile
import time

import config

LATIDO_MAX_SEGUNDOS = 45


def ruta(nombre: str) -> str:
    return os.path.join(config.directorio_estado(), nombre)


def leer() -> dict:
    try:
        with open(ruta("estado.json"), "r", encoding="utf-8") as f:
            datos = json.load(f)
            return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def escribir(datos: dict) -> None:
    destino = ruta("estado.json")
    carpeta = os.path.dirname(destino)
    fd, temporal = tempfile.mkstemp(prefix=".estado-", dir=carpeta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        os.replace(temporal, destino)
    except OSError:
        try:
            os.remove(temporal)
        except OSError:
            pass


def demonio_vivo(datos: dict = None) -> bool:
    datos = datos if datos is not None else leer()
    return (time.time() - float(datos.get("latido", 0) or 0)) < LATIDO_MAX_SEGUNDOS


def pausado() -> bool:
    return os.path.exists(ruta("pausa"))


def pausar(activar: bool) -> None:
    p = ruta("pausa")
    if activar:
        with open(p, "w", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
    elif os.path.exists(p):
        os.remove(p)


def senal_guia_silencia(defecto: bool = False) -> bool:
    """¿Silencia el hub cuando ve la señal de la guía? Lo decide el botón del mando; si nunca se ha tocado, la config."""
    try:
        with open(ruta("senal_guia"), encoding="utf-8") as f:
            return f.read().strip() == "1"
    except OSError:
        return bool(defecto)


def activar_senal_guia(activar: bool) -> None:
    with open(ruta("senal_guia"), "w", encoding="utf-8") as f:
        f.write("1" if activar else "0")


def poner_orden(nombre: str) -> None:
    with open(ruta("orden_" + nombre), "w", encoding="utf-8") as f:
        f.write(str(time.time()))


def tomar_orden(nombre: str) -> bool:
    p = ruta("orden_" + nombre)
    if os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            pass
        return True
    return False
