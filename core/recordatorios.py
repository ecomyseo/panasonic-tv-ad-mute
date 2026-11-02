"""
Recordatorios de la guía: cuando empieza un programa, la TV cambia sola a su canal o llega un WhatsApp.

Un fichero por recordatorio en <estado>/recordatorios/<id>.json. El mando web los crea y los borra; el
silenciador, que es el servicio que está siempre en marcha, los dispara. Para que nunca salte dos veces,
antes de actuar se renombra a <id>.hecho: si el renombrado falla, ya lo había tomado otro o se ha borrado.
"""

import json
import os
import re
import tempfile
import time

import config
from epg import normalizar

ACCIONES = ("tele", "whatsapp", "ambos")
CADUCIDAD = 600                 # pasados 10 min del comienzo ya no se actúa (el hub estaba parado)
CONSERVAR_HECHOS = 24 * 3600
_ID = re.compile(r"^[0-9]{6,12}-[a-z0-9]{1,30}$")


def carpeta() -> str:
    ruta = os.path.join(config.directorio_estado(), "recordatorios")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def identificador(canal, inicio) -> str:
    return f"{int(float(inicio))}-{(normalizar(canal) or 'canal')[:30]}"


def _escribir(ruta, datos):
    fd, temporal = tempfile.mkstemp(prefix=".rec-", dir=os.path.dirname(ruta))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        os.replace(temporal, ruta)
    except OSError:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise


def crear(canal, titulo, inicio, fin, accion, numero="", nombre="") -> dict:
    if accion not in ACCIONES:
        raise ValueError("acción no válida")
    rec = {"id": identificador(canal, inicio), "canal": canal, "nombre": nombre or canal, "titulo": titulo,
           "inicio": float(inicio), "fin": float(fin), "accion": accion, "numero": str(numero or ""),
           "creado": time.time()}
    _escribir(os.path.join(carpeta(), rec["id"] + ".json"), rec)
    return rec


def borrar(id_rec) -> bool:
    if not _ID.match(str(id_rec or "")):
        return False
    try:
        os.remove(os.path.join(carpeta(), id_rec + ".json"))
        return True
    except OSError:
        return False


def _leer(extension) -> list:
    lista = []
    raiz = carpeta()
    for nombre in os.listdir(raiz):
        if nombre.startswith(".") or not nombre.endswith(extension):
            continue
        try:
            with open(os.path.join(raiz, nombre), encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(rec, dict) and _ID.match(str(rec.get("id", ""))) and nombre == rec["id"] + extension:
            lista.append(rec)
    lista.sort(key=lambda r: float(r.get("inicio") or 0))
    return lista


def pendientes() -> list:
    return _leer(".json")


def hechos() -> list:
    return _leer(".hecho")


def tomar(rec) -> bool:
    """Lo aparta para actuar UNA sola vez. False si ya no estaba (borrado o tomado)."""
    origen = os.path.join(carpeta(), rec["id"] + ".json")
    try:
        os.replace(origen, origen[:-len(".json")] + ".hecho")
        return True
    except OSError:
        return False


def apuntar(rec, resultado) -> None:
    _escribir(os.path.join(carpeta(), rec["id"] + ".hecho"), dict(rec, resultado=resultado, hecho=time.time()))


def limpiar(ahora=None) -> None:
    ahora = ahora or time.time()
    for rec in hechos():
        if ahora - float(rec.get("hecho") or rec.get("inicio") or 0) > CONSERVAR_HECHOS:
            try:
                os.remove(os.path.join(carpeta(), rec["id"] + ".hecho"))
            except OSError:
                pass
