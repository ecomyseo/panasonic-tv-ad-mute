"""
Seguir una serie o un programa: se marca una vez y, cada vez que sale en la guía, se crea solo su recordatorio
(poner el canal, WhatsApp o las dos cosas), sin apuntarlos uno a uno.

Solo se buscan programas que AÚN NO han empezado y en las próximas HORIZONTE horas, en los canales que tiene tu
tele (los que tienen número) y en el canal donde lo marcaste. Cada recordatorio se crea una sola vez: si lo borras,
no vuelve.
"""

import json
import os
import re
import time
import unicodedata

import estado
import recordatorios

FICHERO = "seguidos.json"
HORIZONTE = 12 * 3600


def plano(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", texto)


def numeros() -> dict:
    """Número de cada canal en la tele (nombre normalizado -> número): el escrito en el mando y el leído del rótulo."""
    from epg import normalizar  # noqa: PLC0415 - epg arrastra la config; aquí solo hace falta al usarlo

    resultado = {}
    for nombre in ("numeros_canal.json", "vuelta.json"):
        try:
            with open(estado.ruta(nombre), encoding="utf-8") as f:
                datos = json.load(f)
        except (OSError, ValueError):
            continue
        for canal, numero in ((datos or {}).get("numeros") or {}).items():
            if str(numero).isdigit() and normalizar(canal):
                resultado[normalizar(canal)] = str(numero)
    return resultado


def _leer() -> list:
    try:
        with open(estado.ruta(FICHERO), encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, list) else []
    except (OSError, ValueError):
        return []


def _escribir(lista):
    ruta = estado.ruta(FICHERO)
    with open(ruta + ".tmp", "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    os.replace(ruta + ".tmp", ruta)


def lista() -> list:
    return [{k: s.get(k) for k in ("id", "titulo", "accion", "canal")} for s in _leer()]


def seguir(titulo, accion="tele", canal="") -> dict:
    titulo = " ".join(str(titulo or "").split())[:120]
    clave = plano(titulo)[:30]
    if len(clave) < 2:
        raise ValueError("Falta el título")
    if accion not in recordatorios.ACCIONES:
        raise ValueError("acción no válida")
    todos = [s for s in _leer() if s.get("id") != clave]
    nuevo = {"id": clave, "titulo": titulo, "accion": accion, "canal": canal, "creado": time.time(), "programados": []}
    todos.append(nuevo)
    _escribir(todos)
    return nuevo


def dejar(id_seguido) -> bool:
    todos = _leer()
    quedan = [s for s in todos if s.get("id") != id_seguido]
    if len(quedan) == len(todos):
        return False
    _escribir(quedan)
    return True


def programar(canales_guia: dict, ahora=None) -> list:
    """
    Crea los recordatorios que falten. `canales_guia` = {canal: [programas como en epg.json]}.
    Devuelve los recordatorios creados.
    """
    from epg import normalizar  # noqa: PLC0415

    ahora = ahora or time.time()
    todos = _leer()
    if not todos:
        return []
    nums = numeros()
    creados = []
    for s in todos:
        objetivo = s["id"]
        hechos = set(s.get("programados") or [])
        for canal, programas in canales_guia.items():
            numero = nums.get(normalizar(canal), "")
            if not numero and canal != s.get("canal"):
                continue
            for p in programas:
                if not (ahora < p["i"] <= ahora + HORIZONTE):
                    continue
                if plano(p.get("tb") or p["t"])[:30] != objetivo:
                    continue
                rid = recordatorios.identificador(canal, p["i"])
                if rid in hechos:
                    continue
                hechos.add(rid)
                creados.append(recordatorios.crear(canal, p.get("tb") or p["t"], p["i"], p["f"], s["accion"], numero))
        # Solo se guardan los de lo que aún no ha pasado (que el fichero no crezca para siempre)
        s["programados"] = sorted(r for r in hechos if int(r.split("-", 1)[0]) > ahora - 86400)
    _escribir(todos)
    return creados
