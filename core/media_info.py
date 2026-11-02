"""
Fichas de películas y programas: carátula, nota, año y sinopsis.

Fuentes, por orden:
  1. TMDb (si hay TMDB_API_KEY en la configuración): nota real de los espectadores.
  2. Lo que trae la guía EPG (nota, año, imagen y descripción), si se pasa.
  3. Wikipedia en castellano (solo sinopsis y carátula, sin nota).
Nunca se inventa una nota: si no hay dato, se dice «Sin nota».
"""

import json
import re
import time
import urllib.parse
import urllib.request

import config

UA = {"User-Agent": "PanasonicTVHub/2.0 (SmartTV Media)"}
_cache = {}
CACHE_SEGUNDOS = 6 * 3600


def _get_json(url, timeout=5):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def limpiar_titulo(titulo: str) -> str:
    t = re.sub(r"\(.*?\)|\[.*?\]", "", titulo or "")
    t = re.sub(r"\s+T\d+(\s*E\d+)?\b.*$", "", t)
    t = re.sub(r"\b(HD|TDT|\d{3,4}p)\b", "", t)
    return re.sub(r"\s+", " ", t).strip(" -:")


class MediaInfoService:
    @staticmethod
    def buscar_info_pelicula(titulo: str, epg: dict = None) -> dict:
        titulo_limpio = limpiar_titulo(titulo)
        epg = epg or {}
        if not titulo_limpio:
            return MediaInfoService._ficha("Emisión en directo", "", None, "", "Sin datos de lo que se emite.", "", "guía")

        clave = (titulo_limpio.lower(), epg.get("nota"))
        guardado = _cache.get(clave)
        if guardado and time.time() - guardado[0] < CACHE_SEGUNDOS:
            return guardado[1]

        ficha = (MediaInfoService._tmdb(titulo_limpio)
                 or MediaInfoService._desde_epg(titulo_limpio, epg)
                 or MediaInfoService._wikipedia(titulo_limpio)
                 or MediaInfoService._ficha(titulo_limpio, "", None, "", "No hay ficha disponible para este título.", "", "ninguna"))
        _cache[clave] = (time.time(), ficha)
        return ficha

    @staticmethod
    def _ficha(titulo, anio, nota, descripcion, sinopsis, poster, fuente) -> dict:
        if isinstance(nota, (int, float)) and nota > 0:
            texto_nota = f"⭐ {nota:.1f} / 10"
            insignia = "🏆 Joya recomendada" if nota >= 7.5 else ""
        else:
            texto_nota, insignia, nota = "Sin nota", "", None
        return {
            "title": titulo,
            "year": anio or "",
            "rating": texto_nota,
            "nota": nota,
            "director": descripcion or "",
            "synopsis": sinopsis or "",
            "poster_url": poster or "",
            "badge": insignia,
            "fuente": fuente,
        }

    @staticmethod
    def _tmdb(titulo):
        clave = (config.cargar().get("TMDB_API_KEY") or "").strip()
        if not clave:
            return None
        url = ("https://api.themoviedb.org/3/search/multi?"
               + urllib.parse.urlencode({"api_key": clave, "query": titulo, "language": "es-ES",
                                         "region": "ES", "include_adult": "false"}))
        try:
            datos = _get_json(url)
        except Exception:  # noqa: BLE001 - sin red, clave mala o cuota: se pasa a la siguiente fuente
            return None
        for r in datos.get("results", []):
            if r.get("media_type") not in ("movie", "tv"):
                continue
            fecha = r.get("release_date") or r.get("first_air_date") or ""
            votos = r.get("vote_count") or 0
            nota = r.get("vote_average") if votos >= 20 else None
            poster = f"https://image.tmdb.org/t/p/w342{r['poster_path']}" if r.get("poster_path") else ""
            sinopsis = r.get("overview") or ""
            return MediaInfoService._ficha(r.get("title") or r.get("name") or titulo, fecha[:4], nota,
                                           "Película" if r.get("media_type") == "movie" else "Serie / programa",
                                           sinopsis[:360] + ("..." if len(sinopsis) > 360 else ""), poster, "TMDb")
        return None

    @staticmethod
    def _desde_epg(titulo, epg):
        if not epg or not (epg.get("descripcion") or epg.get("nota")):
            return None
        desc = epg.get("descripcion") or ""
        return MediaInfoService._ficha(titulo, epg.get("anio", ""), epg.get("nota"), epg.get("categoria", ""),
                                       desc[:360] + ("..." if len(desc) > 360 else ""), epg.get("imagen", ""), "guía TV")

    @staticmethod
    def _wikipedia(titulo):
        url = "https://es.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(titulo)
        try:
            datos = _get_json(url, timeout=4)
        except Exception:  # noqa: BLE001
            return None
        if datos.get("type") != "standard":
            return None  # desambiguación o página inexistente
        extracto = datos.get("extract") or ""
        descripcion = datos.get("description") or ""
        anio = re.search(r"\b(19\d\d|20\d\d)\b", descripcion + " " + extracto)
        return MediaInfoService._ficha(datos.get("title", titulo), anio.group(1) if anio else "", None, descripcion,
                                       extracto[:360] + ("..." if len(extracto) > 360 else ""),
                                       (datos.get("thumbnail") or {}).get("source", ""), "Wikipedia")
