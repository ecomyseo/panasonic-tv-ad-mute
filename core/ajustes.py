"""
Ajustes que se cambian desde el mando web (pantalla «🛠️ Opciones del hub»), guardados en <estado>/ajustes.json.

Son de esta casa y no van al repositorio: la clave de TMDb, la dirección y el token de Home Assistant, la IP del
móvil... El servicio los relee cuando cambia el fichero, sin reiniciar nada. Lo que no se ha tocado nunca vale lo de
DEFECTOS. Todo lo que hace algo por su cuenta (despertador, apagar al salir, modo noche) viene APAGADO.
"""

import ipaddress
import json
import os
import re
import secrets
import tempfile

import estado

FICHERO = "ajustes.json"
SECRETOS = ("tmdb_clave", "ha_token", "clave_avisos")

DEFECTOS = {
    # Volumen
    "volumen_por_canal": True,        # recuerda el volumen de cada canal y lo pone al cambiar
    "noche_activo": False,            # modo noche: el volumen no pasa de un tope en esa franja
    "noche_desde": "23:00",
    "noche_hasta": "07:00",
    "noche_tope": 15,
    # Despertador
    "despertador_activo": False,
    "despertador_hora": "07:30",
    "despertador_dias": "12345",      # 1 = lunes ... 7 = domingo
    "despertador_canal": "1",
    "despertador_volumen": 12,
    # Apagar la tele al salir de casa
    "salir_activo": False,
    "salir_ip": "",                   # IP del móvil en la WiFi de casa
    "salir_minutos": 20,
    # Botón del mando que enseña la ficha de lo que echan: amarillo, verde, info_doble (dos veces «i») o no
    "boton_ficha": "amarillo",
    # Otros
    "tv_mac": "",                     # para encender por red (vacío = se busca en la tabla ARP)
    "tmdb_clave": "",                 # TMDb gratuita: nota, carátula y en qué plataformas está sin anuncios
    # Home Assistant (luces, llamada, timbre, avisos de la casa)
    "ha_url": "",
    "ha_token": "",
    "ha_luces": "",                   # light.salon, light.tira ... separadas por comas
    "ha_brillo_cine": 15,             # % de brillo en modo cine
    "ha_cine": False,                 # modo cine: luces bajas con las películas
    "ha_sensor_llamada": "",          # sensor.<movil>_phone_state de la app de Home Assistant
    "ha_timbre": "",                  # binary_sensor / event del timbre
    "ha_camara": "",                  # camera.<puerta>: foto en la tele cuando llaman
    "clave_avisos": "",               # la usa Home Assistant para mandar avisos a la tele (/api/aviso_casa)
    # Ambilight (HyperHDR con una cámara que mira la pantalla y una tira LED)
    "hyperhdr_url": "",
}

_HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_ENTIDAD = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
_memoria = {"clave": None, "datos": None}


def _ruta():
    return estado.ruta(FICHERO)


def leer() -> dict:
    """DEFECTOS con lo guardado encima (con caché por fecha del fichero)."""
    ruta = _ruta()
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        mtime = None
    if (ruta, mtime) != _memoria["clave"] or _memoria["datos"] is None:
        guardado = {}
        if mtime is not None:
            try:
                with open(ruta, encoding="utf-8") as f:
                    guardado = json.load(f)
            except (OSError, ValueError):
                guardado = {}
        datos = dict(DEFECTOS)
        datos.update({k: v for k, v in (guardado if isinstance(guardado, dict) else {}).items() if k in DEFECTOS})
        _memoria.update(clave=(ruta, mtime), datos=datos)
    return dict(_memoria["datos"])


def publico() -> dict:
    """Para el mando: los secretos no salen, solo si están puestos."""
    datos = leer()
    for clave in SECRETOS:
        datos[clave] = bool(datos.get(clave))
    return datos


def _valor(clave, valor):
    """Valida y convierte; ValueError con el motivo si no vale."""
    defecto = DEFECTOS[clave]
    if isinstance(defecto, bool):
        return str(valor).strip().lower() in ("1", "true", "on", "si", "sí")
    if isinstance(defecto, int):
        try:
            numero = int(str(valor).strip())
        except ValueError:
            raise ValueError(f"«{clave}» tiene que ser un número") from None
        limites = {"noche_tope": (0, 100), "despertador_volumen": (0, 100), "salir_minutos": (5, 240),
                   "ha_brillo_cine": (1, 100)}.get(clave, (0, 100000))
        if not limites[0] <= numero <= limites[1]:
            raise ValueError(f"«{clave}» tiene que estar entre {limites[0]} y {limites[1]}")
        return numero
    texto = " ".join(str(valor or "").split())
    if clave in ("noche_desde", "noche_hasta", "despertador_hora"):
        if not _HORA.match(texto):
            raise ValueError("La hora va como 23:00")
    elif clave == "despertador_dias":
        if not texto or not set(texto) <= set("1234567"):
            raise ValueError("Los días van como 12345 (1 = lunes, 7 = domingo)")
        texto = "".join(sorted(set(texto)))
    elif clave == "boton_ficha":
        if texto not in ("amarillo", "verde", "info_doble", "no"):
            raise ValueError("El botón de la ficha es amarillo, verde, info_doble o no")
    elif clave == "despertador_canal":
        if not (texto.isdigit() and len(texto) <= 4):
            raise ValueError("El canal del despertador tiene que ser un número")
    elif clave == "salir_ip" and texto:
        try:
            ip = ipaddress.ip_address(texto)
            if not ip.is_private or ip.is_loopback:
                raise ValueError
        except ValueError:
            raise ValueError("La IP del móvil tiene que ser de la red de casa (192.168...)") from None
    elif clave == "tv_mac" and texto:
        limpio = re.sub(r"[^0-9A-Fa-f]", "", texto)
        if len(limpio) != 12:
            raise ValueError("La MAC de la tele tiene 12 cifras hexadecimales")
        texto = ":".join(limpio[i:i + 2] for i in range(0, 12, 2)).lower()
    elif clave in ("ha_url", "hyperhdr_url") and texto:
        if not re.match(r"^https?://[^\s/]+(:\d+)?(/.*)?$", texto):
            raise ValueError("La dirección va como http://192.168.1.10:8123")
        texto = texto.rstrip("/")
    elif clave == "ha_luces" and texto:
        entidades = [e.strip() for e in texto.split(",") if e.strip()]
        if not all(_ENTIDAD.match(e) for e in entidades):
            raise ValueError("Las luces van como light.salon, light.tira")
        texto = ",".join(entidades)
    elif clave in ("ha_sensor_llamada", "ha_timbre", "ha_camara") and texto:
        if not _ENTIDAD.match(texto):
            raise ValueError(f"«{texto}» no es una entidad de Home Assistant (dominio.nombre)")
    return texto[:500]


def guardar(cambios: dict) -> dict:
    """Guarda lo que venga (solo claves conocidas). Un secreto vacío no borra el que hay: se borra con «-»."""
    datos = leer()
    for clave, valor in (cambios or {}).items():
        if clave not in DEFECTOS:
            continue
        if clave in SECRETOS and str(valor).strip() == "":
            continue
        if clave in SECRETOS and str(valor).strip() == "-":
            datos[clave] = ""
            continue
        datos[clave] = _valor(clave, valor)
    guardado = {k: v for k, v in datos.items() if v != DEFECTOS[k]}
    carpeta = os.path.dirname(_ruta())
    fd, temporal = tempfile.mkstemp(prefix=".ajustes-", dir=carpeta)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(guardado, f, ensure_ascii=False, indent=1)
    os.replace(temporal, _ruta())
    _memoria["datos"] = None
    return leer()


def clave_avisos() -> str:
    """La clave con que Home Assistant manda avisos a la tele; se crea la primera vez."""
    datos = leer()
    if not datos["clave_avisos"]:
        datos = guardar({"clave_avisos": secrets.token_urlsafe(18)})
    return datos["clave_avisos"]


def en_franja(minuto_del_dia: int, desde: str, hasta: str) -> bool:
    """¿Está ese minuto del día (0-1439) dentro de la franja? La franja puede pasar de medianoche."""
    a = int(desde[:2]) * 60 + int(desde[3:])
    b = int(hasta[:2]) * 60 + int(hasta[3:])
    if a == b:
        return True
    return a <= minuto_del_dia < b if a < b else (minuto_del_dia >= a or minuto_del_dia < b)
