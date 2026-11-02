#!/usr/bin/env python3
"""
Guía de programación (EPG) de la TDT española.

Descarga la guía XMLTV de dobleM (sin códigos de color), la lee en streaming
para no cargar 50 MB en memoria y guarda solo una ventana corta (de 1 hora antes
a VENTANA_HORAS después, unas 30) en epg.json, en la carpeta de estado compartida.

Uso directo:  python3 epg.py --actualizar      (descarga ahora)
              python3 epg.py "Antena 3 HD"     (qué se emite ahora)
"""

import gzip
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

VENTANA_HORAS = 30  # la guía completa del mando enseña hasta mañana a esta hora
_RE_NOTA = re.compile(r"★\s*(\d+(?:[.,]\d+)?)\s*/\s*10")
_RE_ANIO = re.compile(r"\b(19\d\d|20\d\d)\b")
_RE_TEMPORADA = re.compile(r"\s+T\d+(\s*E\d+)?\b.*$")


def normalizar(nombre: str) -> str:
    texto = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"[^a-z0-9]", "", texto)
    return re.sub(r"(hd|uhd|4k)$", "", texto)


def _hora(valor: str) -> float:
    return datetime.strptime(valor.strip(), "%Y%m%d%H%M%S %z").timestamp()


class GuiaEPG:
    _memoria = {"mtime": 0.0, "datos": None}

    def __init__(self, cfg=None):
        self.cfg = cfg or config.cargar()
        self.url = self.cfg.get("EPG_URL") or config.DEFECTOS["EPG_URL"]
        self.refresco = config.entero(self.cfg, "EPG_HORAS_REFRESCO", 4) * 3600
        self.ruta = os.path.join(config.directorio_estado(self.cfg), "epg.json")

    # --------------------------------------------------------- descarga
    def antiguedad(self) -> float:
        try:
            return time.time() - os.path.getmtime(self.ruta)
        except OSError:
            return float("inf")

    def necesita_actualizar(self) -> bool:
        return self.antiguedad() > self.refresco

    def actualizar(self, forzar: bool = False) -> bool:
        if not forzar and not self.necesita_actualizar():
            return True
        ahora = time.time()
        desde, hasta = ahora - 3600, ahora + VENTANA_HORAS * 3600
        canales = {}
        req = urllib.request.Request(self.url, headers={"User-Agent": "PanasonicTVHub/2.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            flujo = gzip.GzipFile(fileobj=resp) if self.url.endswith(".gz") else resp
            raiz = None
            for evento, elem in ET.iterparse(flujo, events=("start", "end")):
                if evento == "start":
                    if raiz is None:
                        raiz = elem
                    continue
                if elem.tag != "programme":
                    if elem.tag == "channel" and raiz is not None:
                        raiz.clear()
                    continue
                try:
                    inicio, fin = _hora(elem.get("start", "")), _hora(elem.get("stop", ""))
                except ValueError:
                    elem.clear()
                    continue
                if fin > desde and inicio < hasta:
                    canales.setdefault(elem.get("channel", ""), []).append(self._programa(elem, inicio, fin))
                elem.clear()
                if raiz is not None:
                    raiz.clear()
        if not canales:
            return False
        for lista in canales.values():
            lista.sort(key=lambda p: p["i"])
        datos = {"generado": ahora, "url": self.url, "canales": canales}
        carpeta = os.path.dirname(self.ruta)
        fd, temporal = tempfile.mkstemp(prefix=".epg-", dir=carpeta)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)
        os.replace(temporal, self.ruta)
        return True

    @staticmethod
    def _programa(elem, inicio, fin) -> dict:
        def texto(etiqueta):
            nodo = elem.find(etiqueta)
            return (nodo.text or "").strip() if nodo is not None and nodo.text else ""

        titulo = texto("title")
        sub = texto("sub-title")
        nota = _RE_NOTA.search(sub)
        anio = _RE_ANIO.search(sub)
        icono = elem.find("icon")
        desc = texto("desc")
        return {
            "i": inicio,
            "f": fin,
            "t": titulo,
            "tb": _RE_TEMPORADA.sub("", titulo).strip(),
            "d": desc[:420] + ("..." if len(desc) > 420 else ""),
            "c": texto("category"),
            "img": icono.get("src", "") if icono is not None else "",
            "nota": float(nota.group(1).replace(",", ".")) if nota else None,
            "anio": anio.group(1) if anio else "",
        }

    # ---------------------------------------------------------- consulta
    def _datos(self):
        try:
            mtime = os.path.getmtime(self.ruta)
        except OSError:
            return None
        if GuiaEPG._memoria["mtime"] != mtime:
            try:
                with open(self.ruta, "r", encoding="utf-8") as f:
                    GuiaEPG._memoria = {"mtime": mtime, "datos": json.load(f)}
            except (OSError, ValueError):
                return None
        return GuiaEPG._memoria["datos"]

    def buscar_canal(self, nombre: str):
        datos = self._datos()
        if not datos or not nombre:
            return None
        objetivo = normalizar(nombre)
        if not objetivo:
            return None
        claves = list(datos["canales"].keys())
        for clave in claves:
            if normalizar(clave) == objetivo:
                return clave
        for clave in claves:
            n = normalizar(clave)
            if n and (n.startswith(objetivo) or objetivo.startswith(n)):
                return clave
        return None

    @staticmethod
    def _publico(p) -> dict:
        if not p:
            return None
        return {
            "titulo": p["t"],
            "titulo_busqueda": p.get("tb") or p["t"],
            "inicio": datetime.fromtimestamp(p["i"]).strftime("%H:%M"),
            "fin": datetime.fromtimestamp(p["f"]).strftime("%H:%M"),
            "inicio_ts": p["i"],
            "fin_ts": p["f"],
            "progreso": None,
            "descripcion": p.get("d", ""),
            "categoria": p.get("c", ""),
            "imagen": p.get("img", ""),
            "nota": p.get("nota"),
            "anio": p.get("anio", ""),
        }

    def ahora(self, nombre_canal: str) -> dict:
        resultado = {"canal": nombre_canal, "canal_epg": None, "actual": None, "siguiente": None,
                     "aviso": None, "titulo": None}
        datos = self._datos()
        if not datos:
            resultado["aviso"] = "La guía aún no se ha descargado"
            return resultado
        clave = self.buscar_canal(nombre_canal)
        if not clave:
            resultado["aviso"] = f"El canal «{nombre_canal}» no está en la guía"
            return resultado
        resultado["canal_epg"] = clave
        ahora = time.time()
        lista = datos["canales"].get(clave, [])
        for idx, p in enumerate(lista):
            if p["i"] <= ahora < p["f"]:
                actual = self._publico(p)
                actual["progreso"] = round(100 * (ahora - p["i"]) / max(1, p["f"] - p["i"]))
                resultado["actual"] = actual
                resultado["titulo"] = actual["titulo"]
                resultado["siguiente"] = self._publico(lista[idx + 1]) if idx + 1 < len(lista) else None
                return resultado
        futuros = [p for p in lista if p["i"] > ahora]
        resultado["siguiente"] = self._publico(futuros[0]) if futuros else None
        resultado["aviso"] = "Sin datos de este momento: la guía está desfasada"
        return resultado

    def clave_exacta(self, nombre: str):
        """El canal de la guía que se llama igual (sin mirar HD, mayúsculas ni espacios). Nada de parecidos."""
        datos = self._datos()
        objetivo = normalizar(nombre)
        if not datos or not objetivo:
            return None
        return next((c for c in datos["canales"] if normalizar(c) == objetivo), None)

    def en_emision(self, clave: str):
        """(lo de ahora, lo siguiente) de un canal de la guía, en el formato público."""
        datos = self._datos()
        lista = datos["canales"].get(clave, []) if datos else []
        t = time.time()
        actual = next((p for p in lista if p["i"] <= t < p["f"]), None)
        siguiente = next((p for p in lista if p["i"] > t), None)
        publico = self._publico(actual)
        if publico:
            publico["progreso"] = round(100 * (t - actual["i"]) / max(1, actual["f"] - actual["i"]))
        return publico, self._publico(siguiente)

    def buscar_programas(self, texto: str, limite: int = 200):
        """Programas aún por empezar cuyo título contiene el texto (sin tildes ni mayúsculas).
        None si la guía no se ha descargado."""
        datos = self._datos()
        if not datos:
            return None
        objetivo = _plano(texto)
        if len(objetivo) < 2:
            return []
        ahora = time.time()
        encontrados = []
        for canal, lista in datos["canales"].items():
            for p in lista:
                if p["i"] > ahora and objetivo in _plano(p["t"]):
                    encontrados.append(dict(self._publico(p), canal=canal))
        encontrados.sort(key=lambda r: r["inicio_ts"])
        return encontrados[:limite]

    def programa(self, canal: str, inicio: float):
        """El programa de ese canal que empieza a esa hora (para no fiarse de lo que mande el móvil)."""
        datos = self._datos()
        if not datos:
            return None
        for p in datos["canales"].get(canal, []):
            if abs(p["i"] - float(inicio)) < 1:
                return p
        return None


def _plano(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", texto)


def main():
    guia = GuiaEPG()
    if len(sys.argv) > 1 and sys.argv[1] == "--actualizar":
        t0 = time.time()
        ok = guia.actualizar(forzar=True)
        datos = guia._datos() or {"canales": {}}
        print(f"Guía {'actualizada' if ok else 'SIN datos'}: {len(datos['canales'])} canales "
              f"en {time.time() - t0:.1f} s -> {guia.ruta}")
        sys.exit(0 if ok else 1)
    canal = sys.argv[1] if len(sys.argv) > 1 else "La 1 HD"
    print(json.dumps(guia.ahora(canal), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
