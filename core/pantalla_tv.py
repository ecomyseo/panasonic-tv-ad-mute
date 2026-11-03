"""
Lo que pone la pantalla de la tele, leído con el «Lector» de la app de avisos (avisos_app, `am instrument`).

Sirve para la guía de la TDT: con la guía abierta, el programa marcado sale en la parte de arriba
(`epg_program_info_name`, `epg_program_info_time`, `epg_program_info_detail`) y la fila del canal marcado lleva la
marca de seleccionada. Medido en la tele el 3/11/2026 (EPGEuActivity de com.mediatek.wwtv.tvcenter).

`uiautomator dump` no vale ahí: espera a que la pantalla esté quieta y el reloj de la guía no para nunca.
"""

import re
import time
from datetime import date, datetime, timedelta

LECTOR = "es.gmartos.tvhub.avisos/.Lector"
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "sept": 9,
         "oct": 10, "nov": 11, "dic": 12}
DIAS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
_RE_HORAS = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
_RE_FECHA = re.compile(r"(\d{1,2})\s+([a-zA-Zé]{3,4})\.?\s+(\d{4})")


def es_la_guia(foco: str) -> bool:
    """¿La ventana delante es la guía de la TDT? (la de Europa es ...epg.eu.EPGEuActivity)"""
    return ".epg." in (foco or "") and "Activity" in (foco or "")


def parsear(salida: str):
    """Las filas que devuelve el Lector: [{id, texto, marcas}, ...]. [] si no ha podido leer."""
    m = re.search(r"INSTRUMENTATION_RESULT: textos=(.*?)(?:\nINSTRUMENTATION_|\Z)", salida or "", re.S)
    filas = []
    for linea in (m.group(1) if m else "").splitlines():
        partes = linea.split("\t")
        if len(partes) >= 3 and partes[1].strip():
            filas.append({"id": partes[0], "texto": partes[1].strip(), "marcas": partes[2]})
    return filas


def leer(tv):
    """Lee la pantalla de la tele (tarda unos 4 s: arranca el Lector). [] si no se puede."""
    return parsear(tv.shell("am", "instrument", "-w", LECTOR, timeout=25))


def _texto(filas, ident, marcado=False):
    for f in filas:
        if f["id"] == ident and (not marcado or "S" in f["marcas"] or "F" in f["marcas"]):
            return f["texto"]
    return ""


def _momento(texto, hoy=None):
    """'15:26 - 16:15   Martes , 3 nov 2026' -> (inicio_ts, fin_ts). (None, None) si no se entiende."""
    horas = _RE_HORAS.search(texto or "")
    if not horas:
        return None, None
    dia = hoy or date.today()
    fecha = _RE_FECHA.search(texto)
    if fecha and fecha.group(2).lower() in MESES:
        try:
            dia = date(int(fecha.group(3)), MESES[fecha.group(2).lower()], int(fecha.group(1)))
        except ValueError:
            pass
    h1, m1, h2, m2 = (int(x) for x in horas.groups())
    inicio = datetime(dia.year, dia.month, dia.day, h1 % 24, m1)
    fin = datetime(dia.year, dia.month, dia.day, h2 % 24, m2)
    if fin <= inicio:
        fin += timedelta(days=1)
    return inicio.timestamp(), fin.timestamp()


def programa_de_la_guia(filas, hoy=None):
    """El programa marcado en la guía de la tele, o None si lo que se ve no es la guía."""
    titulo = _texto(filas, "epg_program_info_name")
    if not titulo:
        return None
    inicio, fin = _momento(_texto(filas, "epg_program_info_time"), hoy)
    return {
        "titulo": titulo,
        "canal": _texto(filas, "epg_channel_name", marcado=True),
        "numero": _texto(filas, "epg_channel_number", marcado=True),
        "detalle": _texto(filas, "epg_program_info_detail"),
        "tipo": _texto(filas, "epg_program_info_type"),
        "inicio_ts": inicio,
        "fin_ts": fin,
    }


def titulo_para_buscar(titulo: str):
    """'SERIE.- "Falcon Crest." (1981)' -> ('Falcon Crest', '1981'). Para buscar la ficha fuera."""
    t = re.sub(r"^[A-ZÁÉÍÓÚÑ ]{3,}\s*\.?-\s*", "", titulo or "").strip()
    anio = ""
    m = re.search(r"\((\d{4})\)\s*$", t)
    if m:
        anio, t = m.group(1), t[:m.start()].strip()
    t = re.split(r"\s+-\s*(?:Temporada|T\d|Ep\.)", t)[0]
    t = t.strip(" \"'«».").strip()
    return t or (titulo or "").strip(), anio


def _hora(ts, ahora):
    if not ts:
        return ""
    d = datetime.fromtimestamp(ts)
    if d.date() == datetime.fromtimestamp(ahora).date():
        return d.strftime("%H:%M")
    return f"{DIAS[d.weekday()]} {d.day} {d.strftime('%H:%M')}"


def como_programa(marcado, ahora=None):
    """Lo de la guía de la tele en el formato público de epg.py (cuando la guía del hub no lo tiene)."""
    ahora = ahora or time.time()
    busqueda, anio = titulo_para_buscar(marcado["titulo"])
    return {
        "titulo": marcado["titulo"],
        "titulo_busqueda": busqueda,
        "inicio": _hora(marcado.get("inicio_ts"), ahora),
        "fin": datetime.fromtimestamp(marcado["fin_ts"]).strftime("%H:%M") if marcado.get("fin_ts") else "",
        "inicio_ts": marcado.get("inicio_ts"),
        "fin_ts": marcado.get("fin_ts"),
        "progreso": None,
        "descripcion": marcado.get("detalle", ""),
        "categoria": marcado.get("tipo", ""),
        "imagen": "",
        "nota": None,
        "anio": anio,
        "creditos": {},
    }
