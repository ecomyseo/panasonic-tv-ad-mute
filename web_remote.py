#!/usr/bin/env python3
"""
Panasonic Google TV Web Remote & Smart Hub
Mando web táctil para el móvil: silenciador de anuncios, guía de lo que se emite
con su ficha, mando a distancia, apps, temporizador, privacidad y salud de la Raspberry.
Puerto: WEB_PORT (8080 por defecto).
"""

import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

if getattr(sys, "frozen", False):
    BASE = sys._MEIPASS
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "core"))

import ajustes  # noqa: E402
import dns_hub  # noqa: E402
import avisos_tv  # noqa: E402
import casa as casa_mod  # noqa: E402
import config  # noqa: E402
import estado  # noqa: E402
import ficha_tv  # noqa: E402
import pi_salud  # noqa: E402
import recordatorios  # noqa: E402
import presencia  # noqa: E402
import seguir  # noqa: E402
import senal_guia  # noqa: E402
import sintonizador  # noqa: E402
import whatsapp_privado  # noqa: E402
from epg import GuiaEPG, normalizar  # noqa: E402
from media_info import MediaInfoService  # noqa: E402
from privacy_shield import PrivacyShield  # noqa: E402
from tv_manager import PanasonicTVManager  # noqa: E402

CFG = config.cargar()
TV_IP = CFG["TV_IP"]
PORT = config.entero(CFG, "WEB_PORT", 8080)
MUTE_DURATION = config.entero(CFG, "MUTE_DURATION", 150)

tv = PanasonicTVManager(tv_ip=TV_IP)
privacy = PrivacyShield(tv_ip=TV_IP)
avisos = avisos_tv.AvisosTV(tv, CFG)
casa = casa_mod.Casa()


def obtener_mi_ip_local():
    """IP de este equipo en la red de casa."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


LOCAL_IP = obtener_mi_ip_local()

# ------------------------------------------------------------ solo desde casa
# El mando escucha en toda la red de casa (para el móvil), pero no atiende a nadie de fuera:
#  1. la dirección de quien pregunta tiene que ser de este equipo o de la red de casa;
#  2. el nombre con el que se le llama también (si no, una web de fuera podría apuntar su
#     nombre a esta IP y leer el mando desde el navegador: «DNS rebinding»);
#  3. las órdenes solo se aceptan desde la propia página del mando, no desde otra web abierta
#     en el navegador del móvil o del PC.
REDES_DE_CASA = [ipaddress.ip_network(r) for r in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
    "::1/128", "fc00::/7", "fe80::/10")]
SUFIJOS_DE_CASA = (".local", ".lan", ".home", ".internal", ".localdomain", ".home.arpa", ".fritz.box")
NOMBRES_DE_CASA = ({n.lower() for n in config.lista(CFG, "WEB_NOMBRES_PERMITIDOS")}
                   | {socket.gethostname().lower(), "localhost"})


def cliente_permitido(ip) -> bool:
    try:
        direccion = ipaddress.ip_address(str(ip or "").split("%")[0])
    except ValueError:
        return False
    if getattr(direccion, "ipv4_mapped", None):
        direccion = direccion.ipv4_mapped
    return any(direccion in red for red in REDES_DE_CASA)


def host_permitido(host) -> bool:
    nombre = str(host or "").strip().lower()
    if not nombre:
        return True
    if nombre.startswith("["):
        nombre = nombre[1:].split("]")[0]
    elif nombre.count(":") == 1:
        nombre = nombre.split(":")[0]
    nombre = nombre.rstrip(".")
    try:
        ipaddress.ip_address(nombre)
        return cliente_permitido(nombre)
    except ValueError:
        pass
    return "." not in nombre or nombre in NOMBRES_DE_CASA or nombre.endswith(SUFIJOS_DE_CASA)


def orden_desde_otra_web(cabeceras) -> bool:
    sitio = (cabeceras.get("Sec-Fetch-Site") or "").lower()
    if sitio and sitio not in ("same-origin", "none"):
        return True
    origen = cabeceras.get("Origin")
    if origen:
        return origen == "null" or urllib.parse.urlparse(origen).netloc.lower() != (cabeceras.get("Host") or "").lower()
    return False

# ------------------------------------------------------------ caché corta
_cache = {}
_cache_lock = threading.Lock()


_refrescando = set()


def _refrescar(clave, funcion):
    try:
        valor = funcion()
        with _cache_lock:
            _cache[clave] = (time.time(), valor)
    except Exception:  # noqa: BLE001 - se queda el valor de antes
        pass
    finally:
        with _cache_lock:
            _refrescando.discard(clave)


def en_cache(clave, funcion, segundos):
    """Lo caducado hace poco se devuelve tal cual y se refresca por detrás: preguntarle a la tele por ADB tarda,
    y en un móvil (Termux) una página del mando llegaba a tardar 6-11 s cada vez que caducaba (medido el 3/11/2026)."""
    ahora = time.time()
    with _cache_lock:
        guardado = _cache.get(clave)
        if guardado and ahora - guardado[0] < segundos:
            return guardado[1]
        if guardado and ahora - guardado[0] < segundos * 6:
            if clave not in _refrescando:
                _refrescando.add(clave)
                threading.Thread(target=_refrescar, args=(clave, funcion), daemon=True).start()
            return guardado[1]
    valor = funcion()
    with _cache_lock:
        _cache[clave] = (time.time(), valor)
    return valor


# ------------------------------------------------------------ WhatsApp (privado, opcional)
def mensajero():
    """Módulo privado mensajero_tv.py (no va en el repositorio). None si no está configurado."""
    return whatsapp_privado.cargar(BASE)


# ------------------------------------------------------------ estado
def estado_completo() -> dict:
    d = estado.leer()
    vivo = estado.demonio_vivo(d)
    if vivo:
        conexion = d.get("conexion") or "sin_conexion"
        canal = d.get("canal") or ""
    else:
        conexion = en_cache("conexion", tv.estado_conexion, 10)
        canal = ""
    if not canal and conexion == "device":
        canal = en_cache("canal", lambda: tv.get_current_channel().get("name", ""), 20)
    encendida = en_cache("encendida", tv.esta_encendida, 20) if conexion == "device" else None
    silenciada = bool(d.get("silenciada")) if vivo else tv.silenciada_por_nosotros
    fin = float(d.get("fin_silencio") or 0) if vivo else tv.fin_silencio
    return {
        "tv_ip": TV_IP,
        "conexion": conexion,
        "encendida": encendida,
        "canal": canal or "Desconocido",
        "auto": {
            "servicio": vivo,
            "pausado": estado.pausado(),
            "silenciada": silenciada,
            "quedan": max(0, int(fin - time.time())) if silenciada and fin else 0,
            "cortes_hoy": int(d.get("cortes_hoy", 0) or 0) if d.get("hoy") == time.strftime("%Y-%m-%d") else 0,
            "minutos_hoy": round(int(d.get("segundos_hoy", 0) or 0) / 60) if d.get("hoy") == time.strftime("%Y-%m-%d") else 0,
            "ultimo_corte": d.get("ultimo_corte"),
            "mute_segundos": MUTE_DURATION,
        },
        "vuelta": resumen_vuelta(d) if vivo else None,
        "apagado_nocturno": CFG.get("APAGADO_NOCTURNO", ""),
        "pi": en_cache("pi", pi_salud.leer, 30),
        "whatsapp": mensajero() is not None,
        "avisos_tv": {"activo": avisos.activo, "modo": en_cache("avisos", avisos.modo, 30)},
        "casa": {"ha": casa.configurada(), "cine": ajustes.leer()["ha_cine"],
                 "ambilight": bool(ajustes.leer()["hyperhdr_url"]), "sintonizador": sintonizador.detectados()},
        "seguidos": seguir.lista(),
        "senal_guia": dict(en_cache("senal_guia", senal_guia.resumen, 15),
                           silencia=estado.senal_guia_silencia(CFG.get("GUIA_SILENCIA", "0").strip() == "1")),
    }


def resumen_vuelta(d) -> dict:
    """Lo que el mando enseña de la vuelta al canal: a qué canal y cuántos segundos faltan."""
    v = d.get("vuelta")
    if not isinstance(v, dict) or v.get("estado") in (None, "inactiva"):
        return {"estado": "inactiva"}
    r = {"estado": v.get("estado"), "origen": v.get("origen") or ""}
    if v.get("hora_vuelta"):
        r["quedan"] = max(0, int(float(v["hora_vuelta"]) - time.time()))
    return r


def ahora_en_emision() -> dict:
    canal = estado_completo()["canal"]
    prog = GuiaEPG(CFG).ahora(canal)
    prog["numero"] = numeros_canal().get(normalizar(prog.get("canal_epg") or ""), "")
    actual = prog.get("actual")
    ficha = MediaInfoService.buscar_info_pelicula(actual["titulo_busqueda"], epg=actual) if actual else None
    plataformas = MediaInfoService.sin_anuncios(actual["titulo_busqueda"]) if actual else []
    return {"epg": prog, "ficha": ficha, "sin_anuncios": plataformas}


# ------------------------------------------------------------ recordatorios
def _leer_json(nombre) -> dict:
    try:
        with open(estado.ruta(nombre), encoding="utf-8") as f:
            datos = json.load(f)
            return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def numeros_canal() -> dict:
    """Número de cada canal en la TV: los que ha escrito el usuario y, por encima, los leídos del rótulo."""
    numeros = {}
    for nombre in ("numeros_canal.json", "vuelta.json"):
        datos = _leer_json(nombre)
        for canal, numero in (datos.get("numeros") or {}).items():
            if str(numero).isdigit() and normalizar(canal):
                numeros[normalizar(canal)] = str(numero)
    return numeros


def apuntar_numero(canal, numero) -> None:
    """Lo escribe el mando web y solo él (vuelta.json es del silenciador)."""
    datos = _leer_json("numeros_canal.json")
    datos.setdefault("numeros", {})[canal] = numero
    ruta = estado.ruta("numeros_canal.json")
    with open(ruta + ".tmp", "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False)
    os.replace(ruta + ".tmp", ruta)


def _hora(ts) -> str:
    return time.strftime("%H:%M", time.localtime(float(ts)))


def buscar_en_guia(texto) -> dict:
    encontrados = GuiaEPG(CFG).buscar_programas(texto)
    if encontrados is None:
        return {"resultados": [], "aviso": "La guía aún no se ha descargado"}
    numeros = numeros_canal()
    resultados = [{"canal": p["canal"], "nombre": p["canal"], "titulo": p["titulo"], "inicio": p["inicio"],
                   "inicio_ts": p["inicio_ts"], "numero": numeros.get(normalizar(p["canal"]), "")}
                  for p in encontrados]
    # Primero los canales que se sabe que están en la TV; dentro de cada grupo, por hora
    resultados.sort(key=lambda r: (not r["numero"], r["inicio_ts"]))
    resultados = resultados[:25]
    return {"resultados": resultados, "aviso": None if resultados else "No sale en las próximas horas de la guía"}


def lista_recordatorios() -> dict:
    def publico(r):
        return {"id": r["id"], "titulo": r.get("titulo", ""), "nombre": r.get("nombre", ""),
                "numero": r.get("numero", ""), "accion": r.get("accion", ""), "hora": _hora(r.get("inicio") or 0),
                "inicio_ts": r.get("inicio"), "resultado": r.get("resultado", "")}

    ahora = time.time()
    hechos = [r for r in recordatorios.hechos() if ahora - float(r.get("hecho") or 0) < 12 * 3600]
    hechos.sort(key=lambda r: float(r.get("hecho") or 0), reverse=True)
    return {"pendientes": [publico(r) for r in recordatorios.pendientes()],
            "hechos": [publico(r) for r in hechos[:5]], "servicio": estado.demonio_vivo()}


# ------------------------------------------------------------ parrilla
# Canales nacionales de la TDT en su orden habitual: salen en la parrilla aunque aún no se sepa su número
PRINCIPALES = ["La 1", "La 2", "Antena 3", "Cuatro", "Telecinco", "laSexta", "24 Horas", "Clan", "Teledeporte",
               "Neox", "Nova", "Mega", "Atreseries", "FDF", "Energy", "Divinity", "Be Mad", "Boing", "Trece",
               "DMAX", "Paramount Network", "DKISS", "Ten", "Real Madrid TV", "GOL PLAY"]
MENSAJE_SEGUNDOS = 15
FICHA_SEGUNDOS = 15


def parrilla() -> dict:
    """Ahora y después en «tus» canales: los que tienen número en la TV y los principales de la TDT."""
    guia = GuiaEPG(CFG)
    if not guia._datos():
        return {"canales": [], "aviso": "La guía aún no se ha descargado"}
    numeros = numeros_canal()
    viendo = normalizar(estado_completo()["canal"])
    claves = {}
    for orden, nombre in enumerate(PRINCIPALES):
        clave = guia.clave_exacta(nombre)
        if clave:
            claves.setdefault(clave, orden)
    for normal in numeros:
        clave = guia.clave_exacta(normal)
        if clave:
            claves.setdefault(clave, len(PRINCIPALES))
    filas = []
    for clave, orden in claves.items():
        actual, siguiente = guia.en_emision(clave)
        filas.append({"canal": clave, "numero": numeros.get(normalizar(clave), ""), "orden": orden,
                      "viendo": normalizar(clave) == viendo, "ahora": actual, "despues": siguiente})
    # Primero los que ya tienen número en tu tele, por su número; luego el resto en el orden de la TDT
    filas.sort(key=lambda f: (not f["numero"], int(f["numero"] or 0), f["orden"]))
    return {"canales": filas, "aviso": None if filas else "Ningún canal de la guía coincide con los de la TDT"}


def ficha_programa(qs) -> dict:
    """Ficha de un programa de la parrilla (por canal y hora de inicio): la de la guía y, si la hay, TMDb."""
    canal = (qs.get("canal", [""])[0] or "").strip()
    try:
        inicio = float(qs.get("inicio", [""])[0])
    except ValueError:
        return {"canal": canal, "programa": None, "ficha": None}
    guia = GuiaEPG(CFG)
    programa = GuiaEPG._publico(guia.programa(canal, inicio))
    if not programa:
        return {"canal": canal, "programa": None, "ficha": None}
    return {"canal": canal, "programa": programa,
            "ficha": MediaInfoService.buscar_info_pelicula(programa["titulo_busqueda"], epg=programa),
            "sin_anuncios": MediaInfoService.sin_anuncios(programa["titulo_busqueda"])}


def guia_canales() -> dict:
    """Todos los canales de la guía: primero los de tu tele (por su número), luego los de la TDT y luego el resto."""
    guia = GuiaEPG(CFG)
    datos = guia._datos()
    if not datos:
        return {"canales": [], "viendo": "", "aviso": "La guía aún no se ha descargado"}
    numeros = numeros_canal()
    principales = {}
    for orden, nombre in enumerate(PRINCIPALES):
        clave = guia.clave_exacta(nombre)
        if clave:
            principales.setdefault(clave, orden)
    vistos, filas = set(), []
    for clave in datos["canales"]:
        normal = normalizar(clave)
        numero = numeros.get(normal, "") if normal not in vistos else ""
        if numero:
            vistos.add(normal)
        grupo = "tuyos" if numero else ("tdt" if clave in principales else "otros")
        filas.append({"canal": clave, "numero": numero, "grupo": grupo})
    peso = {"tuyos": 0, "tdt": 1, "otros": 2}
    filas.sort(key=lambda f: (peso[f["grupo"]], int(f["numero"] or 0), principales.get(f["canal"], 0),
                              normalizar(f["canal"])))
    return {"canales": filas, "viendo": guia.clave_exacta(estado_completo()["canal"]) or "", "aviso": None}


def guia_de_canal(qs) -> dict:
    """Todo lo que trae la guía de un canal: desde hace 3 horas hasta donde llegue (unas 30 horas)."""
    canal = (qs.get("canal", [""])[0] or "").strip()
    datos = GuiaEPG(CFG)._datos()
    if not datos:
        return {"canal": canal, "numero": "", "programas": [], "aviso": "La guía aún no se ha descargado"}
    lista = datos["canales"].get(canal)
    if lista is None:
        return {"canal": canal, "numero": "", "programas": [], "aviso": "Ese canal no está en la guía"}
    ahora = time.time()
    programas = []
    for p in lista:
        if p["f"] <= ahora - 3 * 3600:
            continue
        publico = GuiaEPG._publico(p)
        publico["descripcion"] = publico["descripcion"][:240]
        publico["estado"] = "ahora" if p["i"] <= ahora < p["f"] else ("pasado" if p["f"] <= ahora else "luego")
        if publico["estado"] == "ahora":
            publico["progreso"] = round(100 * (ahora - p["i"]) / max(1, p["f"] - p["i"]))
        programas.append(publico)
    return {"canal": canal, "numero": numeros_canal().get(normalizar(canal), ""), "programas": programas,
            "aviso": None if programas else "La guía no trae programas de este canal"}


def ficha_en_tele(qs):
    """
    La ficha de un programa en la tele. Con la app de avisos sale una tarjeta en el centro, con el cartel y letra
    grande, sin dejar de ver el canal; sin ella, la página /tv_banner en el navegador de la TV.
    """
    canal = (qs.get("canal", [""])[0] or "").strip()
    titulo = (qs.get("title", [""])[0] or "").strip()
    programa = ficha = None
    if canal and qs.get("inicio"):
        datos = ficha_programa(qs)
        programa, ficha = datos["programa"], datos["ficha"]
    elif titulo:
        ficha = MediaInfoService.buscar_info_pelicula(titulo)
    else:
        datos = ahora_en_emision()
        programa, ficha = datos["epg"].get("actual"), datos.get("ficha")
        canal = datos["epg"].get("canal_epg") or datos["epg"].get("canal") or ""
    plataformas = MediaInfoService.sin_anuncios((programa or {}).get("titulo_busqueda") or titulo)
    t = ficha_tv.tarjeta(programa, canal, ficha, plataformas=plataformas)
    if avisos.activo and t["titulo"]:
        if avisos.mostrar(t["titulo"], t["mensaje"], duracion=FICHA_SEGUNDOS, detalle=t["detalle"], imagen=t["imagen"],
                          pie=t["pie"], solo_app=True):
            return 200, "Ficha en la tele"
    return 200, tv.show_banner_on_tv(server_ip=LOCAL_IP, port=PORT, title=titulo or t["titulo"] or None, duration=8)


def ajustes_publicos() -> dict:
    datos = ajustes.publico()
    datos["mac_detectada"] = en_cache("mac_tv", lambda: presencia.mac_de(TV_IP), 600)
    datos["url_avisos"] = (f"http://{LOCAL_IP}:{PORT}/api/aviso_casa?clave={ajustes.clave_avisos()}"
                           "&titulo=Lavadora&texto=Ha+terminado")
    return datos


def privacidad() -> dict:
    datos = dns_hub.estadisticas()
    d = estado.leer()
    datos["dns"] = d.get("dns") if estado.demonio_vivo(d) else None
    datos["dns_privado"] = en_cache("dns_privado", lambda: (tv.shell("settings", "get", "global", "private_dns_mode")
                                                          or "").strip(), 60)
    datos["ip_hub"] = LOCAL_IP
    return datos


def seguir_programa(qs):
    titulo = (qs.get("titulo", [""])[0] or "").strip()
    canal = (qs.get("canal", [""])[0] or "").strip()
    accion = (qs.get("accion", ["tele"])[0] or "tele").strip()
    try:
        s = seguir.seguir(titulo, accion, canal)
    except ValueError as e:
        return 400, str(e)
    datos = GuiaEPG(CFG)._datos()
    nuevos = seguir.programar(datos["canales"]) if datos else []
    return 200, (f"Sigues «{s['titulo']}»" + (f": {len(nuevos)} próximos apuntados" if nuevos else
                                             ": te avisaré cuando salga en la guía"))


def aviso_casa(qs):
    """Avisos que manda Home Assistant (lavadora, puerta...). Con la clave de «🛠️ Opciones del hub»."""
    import hmac  # noqa: PLC0415

    clave = ajustes.leer()["clave_avisos"]
    if not clave or not hmac.compare_digest((qs.get("clave", [""])[0] or "").encode(), clave.encode()):
        return 403, "Clave incorrecta"
    titulo = " ".join((qs.get("titulo", [""])[0] or "").split())[:80] or "Casa"
    texto = " ".join((qs.get("texto", [""])[0] or "").split())[:200]
    if avisos.mostrar(titulo, texto, duracion=12):
        return 200, "Aviso en la tele"
    return 502, "La tele no ha mostrado el aviso"


def poner_canal(qs):
    canal = (qs.get("canal", [""])[0] or "").strip()
    escrito = (qs.get("numero", [""])[0] or "").strip()
    if escrito and not (escrito.isdigit() and len(escrito) <= 4):
        return 400, "El número del canal tiene que ser una cifra"
    numero = escrito or numeros_canal().get(normalizar(canal), "")
    if not numero:
        return 400, "Falta el número del canal en tu tele"
    if tv.esta_encendida() is not True:
        return 409, "La tele está apagada o no responde"
    if escrito and canal:
        apuntar_numero(canal, escrito)
    tv.poner_canal(numero)
    return 200, f"Poniendo {canal or 'el canal'} ({numero})"


def mensaje_tv(qs):
    texto = " ".join((qs.get("texto", [""])[0] or "").split())
    if not texto:
        return 400, "Escribe el mensaje"
    if len(texto) > 200:
        return 400, "El mensaje es demasiado largo (200 letras como mucho)"
    if not avisos.activo:
        return 400, "Los avisos en la TV están desactivados (AVISOS_EN_TV=0)"
    if avisos.mostrar("Mensaje", texto, duracion=MENSAJE_SEGUNDOS):
        return 200, "Mensaje enviado a la tele"
    return 502, "La tele no ha mostrado el mensaje: pulsa «Preparar avisos»"


def crear_recordatorio(qs):
    canal = (qs.get("canal", [""])[0] or "").strip()
    accion = qs.get("accion", ["tele"])[0]
    escrito = (qs.get("numero", [""])[0] or "").strip()
    try:
        inicio = float(qs.get("inicio", [""])[0])
    except ValueError:
        return 400, "Programa no válido"
    if accion not in recordatorios.ACCIONES:
        return 400, "Acción no válida"
    prog = GuiaEPG(CFG).programa(canal, inicio)
    if not prog:
        return 404, "Ese programa no está en la guía"
    if prog["i"] <= time.time():
        return 400, "Ese programa ya ha empezado"
    if escrito and not (escrito.isdigit() and len(escrito) <= 4):
        return 400, "El número del canal tiene que ser una cifra"
    numero = escrito or numeros_canal().get(normalizar(canal), "")
    if accion in ("tele", "ambos") and not numero:
        return 400, "Falta el número del canal en tu tele"
    if accion in ("whatsapp", "ambos") and not mensajero():
        return 400, "WhatsApp no está configurado en este equipo"
    if escrito:
        apuntar_numero(canal, escrito)
    # Sin temporada ni episodio («Pasapalabra T5 E1644» -> «Pasapalabra»): es lo que sale en la TV y el WhatsApp
    rec = recordatorios.crear(canal, prog.get("tb") or prog["t"], prog["i"], prog["f"], accion, numero, nombre=canal)
    return 200, f"Apuntado: «{rec['titulo']}» a las {_hora(rec['inicio'])}"


def hilo_epg():
    """Mantiene la guía al día (en la Raspberry, en un proceso aparte con prioridad baja)."""
    time.sleep(15)
    script = os.path.join(BASE, "core", "epg.py")
    while True:
        try:
            if GuiaEPG(CFG).necesita_actualizar():
                if getattr(sys, "frozen", False):
                    GuiaEPG(CFG).actualizar(forzar=True)
                else:
                    extra = {"preexec_fn": lambda: os.nice(15)} if hasattr(os, "nice") else {}
                    subprocess.run([sys.executable, script, "--actualizar"], timeout=900, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), **extra)
        except Exception as e:  # noqa: BLE001
            print(f"[EPG] No se pudo actualizar la guía: {e}", flush=True)
        time.sleep(1800)


# ------------------------------------------------------------ acciones
ACCIONES_SIMPLES = {
    "vol_up": tv.volume_up,
    "vol_down": tv.volume_down,
    "home": tv.key_home,
    "back": tv.key_back,
    "ch_up": tv.canal_mas,
    "ch_down": tv.canal_menos,
    "guide": tv.guia,
    "encender": tv.encender,
    "apagar": tv.apagar,
    "clean_ram": tv.clean_ram,
    "sleep_30": lambda: tv.start_sleep_timer(30, gradual=True),
    "sleep_60": lambda: tv.start_sleep_timer(60, gradual=True),
    "sleep_cancel": tv.cancel_sleep_timer,
    "privacy_dns": privacy.enable_adguard_private_dns,
    "privacy_dns_off": privacy.disable_private_dns,
}


def ejecutar_accion(cmd: str, qs: dict):
    """Devuelve (código HTTP, mensaje)."""
    if cmd in ACCIONES_SIMPLES:
        return 200, ACCIONES_SIMPLES[cmd]()
    if cmd in ("up", "down", "left", "right", "enter"):
        return 200, tv.key_dpad(cmd)
    vivo = estado.demonio_vivo()
    if cmd == "mute":
        if vivo and estado.leer().get("silenciada"):
            estado.poner_orden("restaurar")
            return 200, "Sonido devuelto"
        return 200, tv.toggle_mute()
    if cmd == "publi":
        if vivo:
            estado.poner_orden("silenciar")
            return 200, f"Silenciando {MUTE_DURATION} s"
        ok = tv.silenciar_temporal(MUTE_DURATION)
        return 200, f"Silenciando {MUTE_DURATION} s" if ok else "La TV ya estaba silenciada"
    if cmd == "restaurar":
        if vivo:
            estado.poner_orden("restaurar")
            return 200, "Devolviendo el sonido"
        return 200, "Sonido devuelto" if tv.restaurar() else "El sonido ya estaba puesto"
    if cmd in ("volver_ya", "no_volver"):
        if not vivo:
            return 200, "El silenciador automático no está en marcha"
        estado.poner_orden(cmd)
        return 200, "Volviendo al canal" if cmd == "volver_ya" else "No se vuelve al canal"
    if cmd == "recordar":
        return crear_recordatorio(qs)
    if cmd == "poner_canal":
        return poner_canal(qs)
    if cmd == "mensaje_tv":
        return mensaje_tv(qs)
    if cmd == "olvidar":
        if recordatorios.borrar(qs.get("id", [""])[0]):
            return 200, "Recordatorio borrado"
        return 404, "Ese recordatorio ya no existe"
    if cmd == "avisos_preparar":
        ok, msg = avisos.preparar()
        return (200 if ok else 502), msg
    if cmd == "avisos_probar":
        if not avisos.activo:
            return 400, "Los avisos en la TV están desactivados (AVISOS_EN_TV=0)"
        if avisos.mostrar("Panasonic TV Hub", "Así se verán los avisos en la tele."):
            return 200, "Aviso enviado a la TV"
        return 502, "La TV no ha mostrado el aviso: pulsa «Preparar avisos»"
    if cmd == "desde_principio":
        if tv.esta_encendida() is not True:
            return 409, "La tele está apagada o no responde"
        return 200, tv.desde_el_principio()
    if cmd == "seguir":
        return seguir_programa(qs)
    if cmd == "dejar_seguir":
        if seguir.dejar((qs.get("id", [""])[0] or "").strip()):
            return 200, "Ya no lo sigues (los recordatorios que ya estaban se quedan)"
        return 404, "No lo seguías"
    if cmd == "casa_probar":
        ok, msg = casa.probar()
        return (200 if ok else 502), msg
    if cmd in ("luces_on", "luces_off"):
        if not casa.configurada():
            return 400, "Falta Home Assistant en «🛠️ Opciones del hub»"
        if casa.luces_encender(cmd == "luces_on"):
            return 200, "Luces encendidas" if cmd == "luces_on" else "Luces apagadas"
        return 502, "Home Assistant no ha contestado (¿has puesto las luces en «🛠️ Opciones del hub»?)"
    if cmd in ("cine_on", "cine_off"):
        ajustes.guardar({"ha_cine": cmd == "cine_on"})
        return 200, "Modo cine activado" if cmd == "cine_on" else "Modo cine desactivado"
    if cmd in ("ambilight_on", "ambilight_off"):
        if not ajustes.leer()["hyperhdr_url"]:
            return 400, "Falta la dirección de HyperHDR en «🛠️ Opciones del hub»"
        if casa.ambilight(cmd == "ambilight_on"):
            return 200, "Ambilight encendido" if cmd == "ambilight_on" else "Ambilight apagado"
        return 502, "HyperHDR no ha contestado"
    if cmd in ("guia_silencia_on", "guia_silencia_off"):
        estado.activar_senal_guia(cmd.endswith("_on"))
        return 200, ("Silenciará con la señal de la guía" if cmd.endswith("_on")
                     else "La señal de la guía solo se apunta, no silencia")
    if cmd == "pausa_auto":
        estado.pausar(True)
        return 200, "Silenciador automático en pausa"
    if cmd == "reanudar_auto":
        estado.pausar(False)
        return 200, "Silenciador automático activo"
    if cmd == "project_banner":
        return ficha_en_tele(qs)
    if cmd == "texto":
        return 200, tv.send_text(qs.get("text", [""])[0])
    if cmd.startswith("app_"):
        nombre = cmd[4:]
        if nombre not in tv.get_known_apps():
            return 400, "Aplicación desconocida"
        return 200, tv.launch_app(nombre)
    if cmd == "whatsapp_ficha":
        m = mensajero()
        if not m:
            return 400, "WhatsApp no está configurado en este equipo"
        modulo, creds = m
        datos = ahora_en_emision()
        actual = datos["epg"].get("actual")
        ficha = datos.get("ficha")
        if not actual or not ficha:
            return 400, "No hay ficha de lo que se emite ahora"
        res = modulo.MensajeroWhatsApp(api_key=creds["API_KEY"]).enviar_ficha_tv(
            creds["TELEFONO_DESTINO"], ficha["title"], datos["epg"].get("canal", ""), ficha["rating"],
            ficha["synopsis"] or actual.get("descripcion", ""))
        if res.get("ok"):
            return 200, "Ficha enviada a tu WhatsApp"
        return 502, f"WhatsApp no la ha aceptado: {res.get('error')}"
    return 400, "Orden desconocida"


# =========================================================================
# PÁGINA DEL BANNER EN LA PANTALLA DE LA TV (/tv_banner) - vista a 3 metros
# =========================================================================
TV_BANNER_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Ficha en la TV</title>
<style>
body{margin:0;background:transparent;overflow:hidden;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;color:#fff;height:100vh;display:flex;align-items:center;justify-content:center}
.banner{background:rgba(9,13,22,.95);border:3px solid #38bdf8;border-radius:28px;padding:3vw 4vw;display:flex;align-items:center;gap:3vw;box-shadow:0 0 60px rgba(0,0,0,.85);animation:sube .4s ease-out;position:relative;width:78vw;max-height:84vh;overflow:hidden}
@keyframes sube{from{transform:scale(.92);opacity:0}to{transform:scale(1);opacity:1}}
.poster{width:15vw;height:22vw;max-height:70vh;border-radius:16px;object-fit:cover;background:#1e293b;flex-shrink:0}
.contenido{flex:1;min-width:0}
.insignia{display:inline-block;background:rgba(245,158,11,.2);color:#fbbf24;font-size:1.6vw;font-weight:700;padding:.4vw 1.2vw;border-radius:20px;margin-bottom:1vw}
.insignia:empty{display:none}
.titulo{font-size:3.6vw;font-weight:800;margin:0 0 1vw;line-height:1.15}
.nota{font-size:2.3vw;font-weight:700;color:#facc15;margin-bottom:1.2vw}
.sinopsis{font-size:1.9vw;color:#e2e8f0;line-height:1.45;display:-webkit-box;-webkit-line-clamp:7;-webkit-box-orient:vertical;overflow:hidden}
.boton{background:linear-gradient(135deg,#e11d48,#be123c);color:#fff;border:2px solid #fda4af;border-radius:18px;padding:1.6vw 2.4vw;font-size:1.7vw;font-weight:800;display:flex;flex-direction:column;align-items:center;gap:4px;text-decoration:none;flex-shrink:0}
.boton:focus,.boton:hover{transform:scale(1.05);background:#f43f5e}
.sub{font-size:1.1vw;font-weight:500;opacity:.9}
.barra{position:absolute;bottom:0;left:0;height:4px;background:#38bdf8;width:100%;animation:cuenta 8s linear forwards}
@keyframes cuenta{from{width:100%}to{width:0}}
</style>
</head>
<body>
<div class="banner">
  <img id="poster" class="poster" alt="">
  <div class="contenido">
    <div id="insignia" class="insignia"></div>
    <div id="titulo" class="titulo">Cargando...</div>
    <div id="nota" class="nota"></div>
    <div id="sinopsis" class="sinopsis"></div>
  </div>
  <a href="#" class="boton" id="boton"><span>🔇 SILENCIAR ANUNCIOS</span><span class="sub">(pulsa OK en el mando)</span></a>
  <div class="barra"></div>
</div>
<script>
var p = new URLSearchParams(window.location.search);
var t = p.get('title');
fetch(t ? '/api/movie_info?title=' + encodeURIComponent(t) : '/api/ahora', {cache: 'no-store'})
  .then(function (r) { return r.json(); })
  .then(function (d) {
    var f = d.ficha || d;
    if (!f || !f.title) { document.getElementById('titulo').textContent = 'Sin ficha disponible'; return; }
    document.getElementById('titulo').textContent = f.title + (f.year ? ' (' + f.year + ')' : '');
    document.getElementById('nota').textContent = f.rating || '';
    document.getElementById('sinopsis').textContent = f.synopsis || '';
    document.getElementById('insignia').textContent = f.badge || '';
    if (f.poster_url) { document.getElementById('poster').src = f.poster_url; }
  })
  .catch(function () {});
document.getElementById('boton').addEventListener('click', function (e) {
  e.preventDefault();
  fetch('/api/action?cmd=publi', {cache: 'no-store'}).then(function () { window.history.back(); });
});
document.getElementById('boton').focus();
setTimeout(function () { window.history.back(); }, 8500);
</script>
</body>
</html>
"""

# =========================================================================
# LO QUE HA BLOQUEADO EL DNS ANTIRRASTREO (/privacidad) - en el móvil, nunca en la tele
# =========================================================================
HTML_PRIVACIDAD = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#090d16">
<title>Qué ha bloqueado el DNS antirrastreo</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:16px;background:#090d16;color:#f8fafc;font-family:-apple-system,"Segoe UI",Roboto,sans-serif;font-size:17px}
.c{max-width:760px;margin:0 auto}
h1{font-size:24px;text-align:center;margin:6px 0 4px}
.sub{text-align:center;color:#b4bfd1;margin-bottom:14px}
.card{background:#151d30;border:1px solid #1e293b;border-radius:16px;padding:14px 16px;margin-bottom:12px}
.cifras{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.cifra{background:#0d1424;border-radius:12px;padding:12px;text-align:center}
.cifra b{display:block;font-size:30px;color:#7dd3fc}
h2{font-size:19px;margin:0 0 10px;color:#7dd3fc}
.fila{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-bottom:1px solid #1e293b;overflow-wrap:anywhere}
.fila:last-child{border-bottom:0}
.fila span:last-child{color:#fbbf24;font-weight:700;flex-shrink:0}
.canal{font-size:18px;font-weight:800;margin:6px 0 4px}
.aviso{background:#3b1414;border:1px solid #7f1d1d;color:#fecaca;border-radius:12px;padding:12px;margin-bottom:12px;line-height:1.45}
.bien{background:#063326;border-color:#065f46;color:#a7f3d0}
.vacio{color:#b4bfd1;text-align:center;padding:10px 0}
.hora{color:#b4bfd1;font-size:15px}
</style>
</head>
<body>
<div class="c">
  <h1>🛡️ DNS antirrastreo</h1>
  <div class="sub">Qué ha bloqueado y en qué canal · últimos 7 días</div>
  <div id="estado"></div>
  <div class="card"><div class="cifras">
    <div class="cifra"><b id="hoy">—</b>hoy</div>
    <div class="cifra"><b id="total">—</b>en 7 días</div>
  </div></div>
  <div class="card"><h2>Por canal</h2><div id="canales"></div></div>
  <div class="card"><h2>Lo más bloqueado</h2><div id="dominios"></div></div>
  <div class="card"><h2>Lo último</h2><div id="ultimos"></div></div>
</div>
<script>
(function () {
  function $(id) { return document.getElementById(id); }
  function fila(izq, der, clase) {
    var f = document.createElement('div');
    f.className = 'fila' + (clase ? ' ' + clase : '');
    var a = document.createElement('span'), b = document.createElement('span');
    a.textContent = izq; b.textContent = der;
    f.appendChild(a); f.appendChild(b);
    return f;
  }
  function vacio(caja, texto) {
    var v = document.createElement('div'); v.className = 'vacio'; v.textContent = texto; caja.appendChild(v);
  }
  function pintar(d) {
    var e = $('estado');
    e.textContent = '';
    var aviso = document.createElement('div');
    if (d.dns && d.dns.activo) {
      aviso.className = 'aviso bien';
      aviso.textContent = 'El DNS del hub está funcionando (' + d.ip_hub + ').';
    } else {
      aviso.className = 'aviso';
      aviso.textContent = 'El DNS del hub está apagado. Se enciende con DNS_ACTIVO=1 (en la Raspberry) y, en la tele, ' +
        'Ajustes → Red → Configuración IP → Estática: DNS 1 = ' + d.ip_hub + ', DNS 2 = la IP del router.';
    }
    e.appendChild(aviso);
    if (d.dns_privado && d.dns_privado !== 'off' && d.dns_privado !== 'null') {
      var p = document.createElement('div');
      p.className = 'aviso';
      p.textContent = 'La tele tiene puesto un DNS privado (' + d.dns_privado + '): así se salta el del hub. ' +
        'Quítalo con «Quitar DNS antirrastreo» en el mando.';
      e.appendChild(p);
    }
    $('hoy').textContent = d.hoy; $('total').textContent = d.total;
    var c = $('canales'); c.textContent = '';
    if (!d.por_canal.length) { vacio(c, 'Nada bloqueado todavía'); }
    d.por_canal.forEach(function (k) {
      var t = document.createElement('div'); t.className = 'canal'; t.textContent = k.canal + ' · ' + k.total;
      c.appendChild(t);
      k.dominios.slice(0, 6).forEach(function (x) { c.appendChild(fila(x.dominio, x.veces)); });
    });
    var dm = $('dominios'); dm.textContent = '';
    if (!d.dominios.length) { vacio(dm, '—'); }
    d.dominios.slice(0, 15).forEach(function (x) { dm.appendChild(fila(x.dominio, x.veces)); });
    var u = $('ultimos'); u.textContent = '';
    if (!d.ultimos.length) { vacio(u, '—'); }
    d.ultimos.slice(0, 30).forEach(function (x) { u.appendChild(fila(x.hora + ' · ' + (x.canal || '?'), x.dominio)); });
  }
  function cargar() {
    fetch('/api/privacidad', {cache: 'no-store'}).then(function (r) { return r.json(); }).then(pintar)
      .catch(function () { $('estado').textContent = 'No hay conexión con el hub'; });
  }
  cargar();
  setInterval(cargar, 30000);
})();
</script>
</body>
</html>
"""

# =========================================================================
# MANDO A DISTANCIA WEB PARA EL MÓVIL (/)
# =========================================================================
HTML_MOBILE_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="theme-color" content="#090d16">
<title>Panasonic Smart Hub</title>
<style>
:root{--bg:#090d16;--card:#151d30;--borde:#1e293b;--primario:#2563eb;--rojo:#e11d48;--oro:#f59e0b;--texto:#f8fafc;--tenue:#b4bfd1;--verde:#10b981}
*{box-sizing:border-box}
body{font-family:-apple-system,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--texto);margin:0;padding:14px;padding-bottom:80px}
.c{max-width:600px;margin:0 auto}
header{text-align:center;margin-bottom:14px}
h1{margin:0;font-size:20px}
.chips{display:flex;gap:6px;justify-content:center;flex-wrap:wrap;margin-top:8px}
.chip{padding:4px 12px;background:#1e293b;border-radius:20px;font-size:12px;color:#38bdf8}
.chip.mal{color:#fca5a5;background:#3b1414}.chip.bien{color:#6ee7b7;background:#063326}
.card{background:var(--card);border:1px solid var(--borde);border-radius:16px;padding:14px;margin-bottom:12px}
.etq{font-size:12px;margin-bottom:8px;color:var(--tenue);font-weight:700;letter-spacing:.5px}
.g2,.g3{display:grid;gap:8px}.g2{grid-template-columns:repeat(2,1fr)}.g3{grid-template-columns:repeat(3,1fr)}
button{font:inherit;cursor:pointer}
.b{background:#252e42;color:#fff;border:1px solid #334155;padding:12px 6px;border-radius:12px;font-size:14px;min-height:46px}
.b:active{background:#3b4760}
.publi{width:100%;padding:16px;background:linear-gradient(135deg,#e11d48,#be123c);color:#fff;border:0;border-radius:14px;font-size:17px;font-weight:700;margin-bottom:10px}
.devolver{width:100%;padding:14px;background:#065f46;color:#fff;border:1px solid #10b981;border-radius:14px;font-size:16px;font-weight:700;margin-bottom:10px;display:none}
.ok{background:var(--primario)!important;font-weight:700}
.dpad{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;max-width:230px;margin:4px auto 8px}
.app{background:#181c33!important;border-color:#3730a3!important;color:#c7d2fe!important}
.priv{background:#064e3b!important;border-color:#059669!important;color:#6ee7b7!important}
.peligro{background:#7f1d1d!important;border-color:#991b1b!important}
.ficha{display:flex;gap:12px;align-items:flex-start}
.poster{width:86px;height:124px;border-radius:10px;object-fit:cover;background:#1e293b;flex-shrink:0}
.poster.vacio{display:flex;align-items:center;justify-content:center;font-size:34px}
.titulo{font-size:19px;font-weight:700;margin:0 0 4px;line-height:1.25}
.insignia{display:inline-block;font-size:11px;font-weight:700;color:var(--oro);background:rgba(245,158,11,.15);padding:2px 8px;border-radius:6px;margin-bottom:4px}
.insignia:empty{display:none}
.nota{font-size:15px;font-weight:600;color:#fbbf24;margin-bottom:4px}
.horario{font-size:15px;color:#38bdf8;margin-bottom:4px}
.sinopsis{font-size:15px;color:var(--tenue);line-height:1.45}
.progreso{height:4px;background:#1e293b;border-radius:2px;margin:8px 0 4px;overflow:hidden}
.progreso div{height:100%;background:#38bdf8;width:0}
.despues{font-size:14px;color:var(--tenue)}
.creditos{margin-top:10px;font-size:15px;line-height:1.45;color:var(--texto)}
.creditos:empty{display:none}
.creditos div{padding:3px 0;border-bottom:1px solid #1e293b}
.creditos b{color:#7dd3fc;font-weight:700}
.fila{display:flex;gap:8px;margin-top:10px}
input[type=text]{flex:1;min-width:0;padding:10px 12px;border-radius:10px;border:1px solid #334155;background:#0b1120;color:#fff;font-size:14px}
.dato{display:flex;justify-content:space-between;font-size:13px;padding:3px 0;border-bottom:1px solid #1e293b}
.dato:last-child{border-bottom:0}
.dato span:last-child{color:var(--tenue);text-align:right}
.aviso{font-size:12px;color:#fca5a5;margin-top:6px}
.aviso:empty{display:none}
select{padding:6px 8px;border-radius:8px;border:1px solid #334155;background:#0b1120;color:#fff;font-size:13px;max-width:190px}
.linea{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;padding:5px 0;border-bottom:1px solid #1e293b}
.linea span{min-width:0;overflow-wrap:anywhere}
.linea.hecho{color:var(--tenue)}
.mini{min-height:36px;padding:4px 12px;flex-shrink:0}
.lista:empty{display:none}
.canal{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #1e293b}
.canal:last-child{border-bottom:0}
.canal.viendo{background:rgba(37,99,235,.12);border-radius:10px;padding:8px 6px}
.num{min-width:42px;height:42px;border-radius:10px;background:#1e293b;color:#93c5fd;font-weight:800;display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0}
.prog{flex:1;min-width:0;font-size:16px;line-height:1.4}
.prog b{display:block;font-size:15px;color:#7dd3fc;overflow-wrap:anywhere}
.prog .ahora{color:var(--texto);font-weight:600;overflow-wrap:anywhere}
.prog .luego{color:var(--tenue);font-size:15px;overflow-wrap:anywhere}
.barra{height:3px;background:#1e293b;border-radius:2px;margin:4px 0;overflow:hidden}
.barra div{height:100%;background:#38bdf8}
.num.sin{color:#475569;background:#111827;font-weight:400}
.toca{cursor:pointer}
.toca:after{content:" ›";color:#38bdf8;font-weight:700}
#hoja-fondo{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:20;display:none;align-items:flex-end;justify-content:center}
#hoja-fondo.abierta{display:flex}
#hoja{background:var(--card);border:1px solid var(--borde);border-radius:18px 18px 0 0;width:100%;max-width:600px;max-height:85vh;overflow-y:auto;padding:16px 16px calc(16px + env(safe-area-inset-bottom))}
#hoja .ficha{margin-bottom:10px}
#hoja-cerrar{float:right;background:none;border:0;color:var(--tenue);font-size:22px;line-height:1;padding:4px 8px}
#toast{position:fixed;left:50%;transform:translateX(-50%);bottom:20px;background:var(--verde);color:#fff;padding:10px 22px;border-radius:20px;display:none;font-size:14px;z-index:9;max-width:90%;text-align:center}
#toast.error{background:#b91c1c}
.oculto{display:none!important}
.guia-abrir{width:100%;font-size:17px;font-weight:700;min-height:52px;margin-bottom:10px}
.sinanuncios{margin-top:8px;font-size:15px;color:#86efac}
.sinanuncios:empty{display:none}
.sinanuncios button{margin:6px 6px 0 0}
.cabecera-botones{display:flex;gap:8px;justify-content:center;margin-top:10px}
#aj-panel{position:fixed;inset:0;background:var(--bg);z-index:16;display:flex;flex-direction:column}
#aj-panel .gp-cuerpo>*{max-width:640px}
.aj-grupo{background:var(--card);border:1px solid var(--borde);border-radius:14px;padding:12px 14px;margin:12px auto 0}
.aj-grupo h3{margin:0 0 8px;font-size:18px;color:#7dd3fc}
.aj-fila{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 0;font-size:16px;border-bottom:1px solid #1e293b}
.aj-fila:last-child{border-bottom:0}
.aj-fila input[type=text],.aj-fila input[type=password],.aj-fila input[type=number],.aj-fila input[type=time]{flex:0 1 230px;min-width:0;padding:9px 10px;border-radius:10px;border:1px solid #334155;background:#0b1120;color:#fff;font-size:16px}
.aj-fila input[type=checkbox]{width:26px;height:26px}
.aj-nota{font-size:14px;color:var(--tenue);margin-top:6px;overflow-wrap:anywhere}
.aj-guardar{display:block;width:100%;max-width:640px;margin:16px auto 0;font-size:18px;min-height:54px}
body.sin-scroll{overflow:hidden}
#guia-panel{position:fixed;inset:0;background:var(--bg);z-index:15;display:flex;flex-direction:column}
.gp-cab{padding:12px 16px 6px;border-bottom:1px solid var(--borde);background:#0d1424}
.gp-cab>*,.gp-cuerpo>*{max-width:760px;margin-left:auto;margin-right:auto}
.gp-fila{display:flex;align-items:center;justify-content:space-between;gap:10px}
.gp-titulo{font-size:24px;font-weight:800}
.gp-cerrar{background:#252e42;border:1px solid #334155;color:#fff;font-size:22px;border-radius:12px;width:50px;height:50px;flex-shrink:0}
#gp-canal{display:block;width:100%;max-width:760px;font-size:18px;padding:12px;margin:10px auto 8px;border-radius:12px}
.gp-chips{display:flex;gap:8px;overflow-x:auto;padding-bottom:8px}
.gp-chip{flex-shrink:0;background:#1e293b;color:#e2e8f0;border:1px solid #334155;border-radius:22px;padding:10px 16px;font-size:16px;font-weight:600}
.gp-chip.activo{background:var(--primario);border-color:#60a5fa;color:#fff}
.gp-cuerpo{flex:1;overflow-y:auto;padding:12px 16px 48px}
.gp-poner{display:block;width:100%;font-size:18px;min-height:52px;margin-bottom:6px}
.gp-dia{font-size:19px;font-weight:800;color:#7dd3fc;text-align:center;padding:20px 0 8px}
.gp-prog{display:flex;gap:16px;align-items:flex-start;padding:14px 12px;border-bottom:1px solid #1e293b;cursor:pointer;border-radius:12px}
.gp-prog.pasado{opacity:.5}
.gp-prog.ahora{background:rgba(37,99,235,.2);border:1px solid #2563eb}
.gp-hora{font-size:22px;font-weight:800;color:#93c5fd;min-width:66px;font-variant-numeric:tabular-nums}
.gp-info{flex:1;min-width:0}
.gp-t{font-size:20px;font-weight:700;line-height:1.3;color:#fff;overflow-wrap:anywhere}
.gp-c{font-size:16px;color:#cbd5e1;margin-top:4px}
.gp-vacio{font-size:18px;color:#cbd5e1;text-align:center;padding:30px 0}
</style>
</head>
<body>
<div class="c">
  <header>
    <h1>Panasonic Smart Hub</h1>
    <div class="chips">
      <span class="chip" id="chip-canal">Canal: ...</span>
      <span class="chip" id="chip-tv">TV: ...</span>
      <span class="chip" id="chip-auto">Silenciador: ...</span>
    </div>
    <div class="cabecera-botones"><button class="b" data-local="aj-abrir">🛠️ Opciones del hub</button></div>
  </header>

  <button class="publi" data-cmd="publi" id="btn-publi">🔇 SILENCIAR ANUNCIOS</button>
  <button class="devolver" data-cmd="restaurar" id="btn-devolver">🔊 DEVOLVER EL SONIDO YA</button>

  <div class="card">
    <div class="etq">AHORA EN EMISIÓN</div>
    <div class="ficha">
      <img id="poster" class="poster" alt="">
      <div style="flex:1;min-width:0">
        <div id="insignia" class="insignia"></div>
        <div id="titulo" class="titulo">Cargando guía...</div>
        <div id="horario" class="horario"></div>
        <div id="nota" class="nota"></div>
        <div id="sinopsis" class="sinopsis"></div>
      </div>
    </div>
    <div id="creditos" class="creditos"></div>
    <div class="progreso"><div id="progreso"></div></div>
    <div class="despues" id="despues"></div>
    <button class="b oculto" id="btn-recordar-sig" data-local="recordar-sig" style="width:100%;margin-top:8px">⏰ Recordar lo siguiente</button>
    <button class="b oculto" id="btn-principio" data-cmd="desde_principio" style="width:100%;margin-top:8px">⏮ Verlo desde el principio (botón azul, LOVEStv)</button>
    <div id="sin-anuncios" class="sinanuncios"></div>
    <div class="aviso" id="aviso-epg"></div>
    <div class="g2" style="margin-top:10px">
      <button class="b" data-cmd="project_banner">📺 Ficha en la TV</button>
      <button class="b oculto" data-cmd="whatsapp_ficha" id="btn-whatsapp">💬 A mi WhatsApp</button>
    </div>
    <div class="fila">
      <input id="buscar" type="text" placeholder="Buscar otra película o serie...">
      <button class="b" style="padding:8px 14px" data-local="buscar">🔍</button>
    </div>
  </div>

  <div class="card">
    <div class="etq">PARRILLA · AHORA Y DESPUÉS</div>
    <button class="b ok guia-abrir" data-local="guia-abrir">📅 Guía completa: todos los canales y horas</button>
    <div class="lista" id="parrilla"></div>
    <div class="aviso" id="parrilla-aviso"></div>
    <button class="b oculto" id="parrilla-mas" data-local="parrilla-mas" style="width:100%;margin-top:8px">Ver todos los canales</button>
  </div>

  <div class="card">
    <div class="etq">SILENCIADOR AUTOMÁTICO</div>
    <div class="dato"><span>Estado</span><span id="auto-estado">...</span></div>
    <div class="dato"><span>Cortes silenciados hoy</span><span id="auto-cortes">0</span></div>
    <div class="dato"><span>Último corte</span><span id="auto-ultimo">—</span></div>
    <div id="vuelta" class="oculto">
      <div class="dato"><span>Vuelta al canal</span><span id="vuelta-texto">—</span></div>
      <div class="g2" style="margin-top:8px">
        <button class="b" data-cmd="volver_ya">↩ Volver ya</button>
        <button class="b" data-cmd="no_volver">✋ No volver</button>
      </div>
    </div>
    <div class="dato"><span>Señal de la guía</span><span id="guia-senal">—</span></div>
    <div class="lista" id="guia-senales"></div>
    <div class="g2" style="margin-top:8px">
      <button class="b" data-cmd="guia_silencia_on" id="btn-guia-on">📡 Silenciar con la señal</button>
      <button class="b oculto" data-cmd="guia_silencia_off" id="btn-guia-off">📡 Solo apuntarla</button>
    </div>
    <div class="g2" style="margin-top:10px">
      <button class="b" data-cmd="pausa_auto" id="btn-pausa">⏸ Pausar</button>
      <button class="b" data-cmd="reanudar_auto" id="btn-reanudar">▶ Reanudar</button>
    </div>
  </div>

  <div class="card oculto" id="card-casa">
    <div class="etq">CASA</div>
    <div class="g2">
      <button class="b" data-cmd="luces_on">💡 Encender luces</button>
      <button class="b" data-cmd="luces_off">💡 Apagar luces</button>
      <button class="b" data-cmd="cine_on" id="btn-cine-on">🎬 Modo cine: poner</button>
      <button class="b oculto" data-cmd="cine_off" id="btn-cine-off">🎬 Modo cine: quitar</button>
      <button class="b" data-cmd="ambilight_on">🌈 Ambilight</button>
      <button class="b" data-cmd="ambilight_off">🌈 Ambilight: apagar</button>
    </div>
  </div>

  <div class="card">
    <div class="etq">RECORDATORIOS</div>
    <div class="linea" style="border-bottom:0">
      <span>Cuando empiece</span>
      <select id="rec-accion">
        <option value="tele">📺 Poner su canal</option>
        <option value="whatsapp" class="solo-wa">💬 Mandarme un WhatsApp</option>
        <option value="ambos" class="solo-wa">📺 + 💬 Las dos cosas</option>
      </select>
    </div>
    <div class="fila" style="margin-top:6px">
      <input id="guia-q" type="text" placeholder="Buscar en la guía (p. ej. Pasapalabra)">
      <button class="b" style="padding:8px 14px" data-local="guia">🔍</button>
    </div>
    <div class="lista" id="guia-res"></div>
    <div class="lista" id="rec-lista" style="margin-top:8px"></div>
    <div class="lista" id="seguidos" style="margin-top:8px"></div>
    <div class="aviso" id="rec-aviso"></div>
    <div class="dato" style="margin-top:10px"><span>Avisos en la pantalla</span><span id="avisos-estado">—</span></div>
    <div class="g2" style="margin-top:8px">
      <button class="b" data-cmd="avisos_preparar">📲 Preparar avisos</button>
      <button class="b" data-cmd="avisos_probar">💬 Probar un aviso</button>
    </div>
  </div>

  <div class="card">
    <div class="g3">
      <button class="b" data-cmd="vol_down">Vol −</button>
      <button class="b" data-cmd="mute">Mute</button>
      <button class="b" data-cmd="vol_up">Vol +</button>
      <button class="b" data-cmd="ch_down">Canal −</button>
      <button class="b" data-cmd="guide">Guía</button>
      <button class="b" data-cmd="ch_up">Canal +</button>
    </div>
  </div>

  <div class="card">
    <div class="dpad">
      <div></div><button class="b" data-cmd="up">▲</button><div></div>
      <button class="b" data-cmd="left">◀</button><button class="b ok" data-cmd="enter">OK</button><button class="b" data-cmd="right">▶</button>
      <div></div><button class="b" data-cmd="down">▼</button><div></div>
    </div>
    <div class="g2">
      <button class="b" data-cmd="back">↩ Volver</button>
      <button class="b" data-cmd="home">⌂ Inicio</button>
      <button class="b" data-cmd="encender">⏻ Encender</button>
      <button class="b peligro" data-cmd="apagar">⏻ Apagar</button>
    </div>
  </div>

  <div class="card">
    <div class="etq">APLICACIONES</div>
    <div class="g2" id="apps"></div>
  </div>

  <div class="card">
    <div class="etq">ESCRIBIR EN LA TV</div>
    <div class="fila" style="margin-top:0">
      <input id="texto" type="text" placeholder="Texto para el buscador de la TV">
      <button class="b" style="padding:8px 14px" data-local="texto">Enviar</button>
    </div>
  </div>

  <div class="card">
    <div class="etq">MENSAJE EN LA PANTALLA DE LA TELE</div>
    <div class="fila" style="margin-top:0">
      <input id="mensaje" type="text" maxlength="200" placeholder="Ej.: ¡A cenar!">
      <button class="b" style="padding:8px 14px" data-local="mensaje">Enviar</button>
    </div>
  </div>

  <div class="card">
    <div class="etq">APAGADO Y MANTENIMIENTO</div>
    <div class="g3">
      <button class="b" data-cmd="sleep_30">⏰ 30 min</button>
      <button class="b" data-cmd="sleep_60">⏰ 60 min</button>
      <button class="b" data-cmd="sleep_cancel">Cancelar</button>
    </div>
    <div class="g2" style="margin-top:8px">
      <button class="b" data-cmd="clean_ram">🧹 Liberar memoria</button>
      <button class="b priv" data-cmd="privacy_dns">🛡️ DNS antirrastreo</button>
    </div>
    <div class="g2" style="margin-top:8px">
      <button class="b" data-cmd="privacy_dns_off">Quitar DNS antirrastreo</button>
      <a class="b" href="/privacidad" target="_blank" rel="noopener" style="text-align:center;text-decoration:none;display:flex;align-items:center;justify-content:center">📊 Qué ha bloqueado</a>
    </div>
    <div class="despues" id="nocturno" style="margin-top:8px"></div>
  </div>

  <div class="card">
    <div class="etq">RASPBERRY PI</div>
    <div class="dato"><span>Temperatura</span><span id="pi-temp">—</span></div>
    <div class="dato"><span>Alimentación</span><span id="pi-alim">—</span></div>
    <div class="dato"><span>Carga / memoria libre</span><span id="pi-carga">—</span></div>
    <div class="dato"><span>Encendida</span><span id="pi-up">—</span></div>
    <div class="dato"><span>Sintonizador USB de TDT</span><span id="pi-tdt">—</span></div>
  </div>
</div>
<div id="aj-panel" class="oculto">
  <div class="gp-cab">
    <div class="gp-fila">
      <div class="gp-titulo">🛠️ Opciones del hub</div>
      <button class="gp-cerrar" data-local="aj-cerrar" aria-label="Cerrar">✕</button>
    </div>
  </div>
  <div class="gp-cuerpo">
    <div class="aj-grupo"><h3>🔊 Volumen</h3>
      <div class="aj-fila"><span>Recordar el volumen de cada canal</span><input type="checkbox" data-aj="volumen_por_canal"></div>
      <div class="aj-fila"><span>Modo noche (volumen con tope)</span><input type="checkbox" data-aj="noche_activo"></div>
      <div class="aj-fila"><span>Desde</span><input type="time" data-aj="noche_desde"></div>
      <div class="aj-fila"><span>Hasta</span><input type="time" data-aj="noche_hasta"></div>
      <div class="aj-fila"><span>Volumen máximo (0-100)</span><input type="number" min="0" max="100" data-aj="noche_tope"></div>
    </div>
    <div class="aj-grupo"><h3>🎬 Ficha de lo que echan (IMDb)</h3>
      <div class="aj-fila"><span>Botón del mando que la enseña (otra vez: la quita)</span>
        <select data-aj="boton_ficha"><option value="amarillo">Amarillo</option><option value="verde">Verde</option>
          <option value="info_doble">«i» dos veces</option><option value="no">Ninguno</option></select></div>
      <div class="aj-fila"><span>Que salga sola al cambiar de canal (una vez por programa)</span><input type="checkbox" data-aj="ficha_al_cambiar"></div>
    </div>
    <div class="aj-grupo"><h3>⏰ Despertador</h3>
      <div class="aj-fila"><span>Encender la tele sola</span><input type="checkbox" data-aj="despertador_activo"></div>
      <div class="aj-fila"><span>Hora</span><input type="time" data-aj="despertador_hora"></div>
      <div class="aj-fila"><span>Días (1 = lunes ... 7 = domingo)</span><input type="text" data-aj="despertador_dias"></div>
      <div class="aj-fila"><span>Canal</span><input type="number" min="1" max="9999" data-aj="despertador_canal"></div>
      <div class="aj-fila"><span>Volumen</span><input type="number" min="0" max="100" data-aj="despertador_volumen"></div>
      <div class="aj-fila"><span>MAC de la tele (para encenderla por red)</span><input type="text" data-aj="tv_mac"></div>
      <div class="aj-nota" id="aj-mac"></div>
    </div>
    <div class="aj-grupo"><h3>🚪 Apagar la tele si me voy</h3>
      <div class="aj-fila"><span>Activado</span><input type="checkbox" data-aj="salir_activo"></div>
      <div class="aj-fila"><span>IP de tu móvil</span><input type="text" data-aj="salir_ip"></div>
      <div class="aj-fila"><span>Minutos sin ver el móvil</span><input type="number" min="5" max="240" data-aj="salir_minutos"></div>
      <button class="b" data-local="usar-movil" style="width:100%;margin-top:8px">📱 Usar este móvil</button>
      <div class="aj-nota">Antes de apagar avisa en la tele; si cambias el volumen o de canal en ese minuto, no la apaga.</div>
    </div>
    <div class="aj-grupo"><h3>🎬 ¿La tienes sin anuncios? (TMDb)</h3>
      <div class="aj-fila"><span>Clave de TMDb</span><input type="password" data-aj="tmdb_clave" autocomplete="off"></div>
      <div class="aj-nota">Gratis en themoviedb.org → Ajustes → API. También da la nota y la carátula de las películas.</div>
    </div>
    <div class="aj-grupo"><h3>🏠 Home Assistant</h3>
      <div class="aj-fila"><span>Dirección</span><input type="text" data-aj="ha_url" placeholder="http://192.168.1.10:8123"></div>
      <div class="aj-fila"><span>Token de larga duración</span><input type="password" data-aj="ha_token" autocomplete="off"></div>
      <div class="aj-fila"><span>Luces (light.salon, light.tira)</span><input type="text" data-aj="ha_luces"></div>
      <div class="aj-fila"><span>Modo cine con las películas</span><input type="checkbox" data-aj="ha_cine"></div>
      <div class="aj-fila"><span>Brillo en modo cine (%)</span><input type="number" min="1" max="100" data-aj="ha_brillo_cine"></div>
      <div class="aj-fila"><span>Sensor de llamadas del móvil</span><input type="text" data-aj="ha_sensor_llamada" placeholder="sensor.movil_phone_state"></div>
      <div class="aj-fila"><span>Timbre</span><input type="text" data-aj="ha_timbre" placeholder="binary_sensor.timbre"></div>
      <div class="aj-fila"><span>Cámara de la puerta</span><input type="text" data-aj="ha_camara" placeholder="camera.puerta"></div>
      <button class="b" data-cmd="casa_probar" style="width:100%;margin-top:8px">🔌 Probar Home Assistant</button>
      <div class="aj-nota" id="aj-url-avisos"></div>
    </div>
    <div class="aj-grupo"><h3>🌈 Ambilight (HyperHDR)</h3>
      <div class="aj-fila"><span>Dirección de HyperHDR</span><input type="text" data-aj="hyperhdr_url" placeholder="http://192.168.1.20:8090"></div>
    </div>
    <button class="b ok aj-guardar" data-local="aj-guardar">💾 Guardar</button>
  </div>
</div>
<div id="guia-panel" class="oculto">
  <div class="gp-cab">
    <div class="gp-fila">
      <div class="gp-titulo">📅 Guía de TV</div>
      <button class="gp-cerrar" data-local="guia-cerrar" aria-label="Cerrar">✕</button>
    </div>
    <select id="gp-canal" aria-label="Canal"></select>
    <div class="gp-chips" id="gp-chips"></div>
  </div>
  <div class="gp-cuerpo" id="gp-cuerpo">
    <button class="b ok gp-poner oculto" id="gp-poner" data-local="gp-poner"></button>
    <div id="gp-lista"></div>
  </div>
</div>
<div id="hoja-fondo" data-local="hoja-fondo">
  <div id="hoja">
    <button id="hoja-cerrar" data-local="hoja-cerrar" aria-label="Cerrar">×</button>
    <div class="etq" id="hoja-canal"></div>
    <div class="ficha">
      <img id="hoja-poster" class="poster" alt="">
      <div style="flex:1;min-width:0">
        <div id="hoja-insignia" class="insignia"></div>
        <div id="hoja-titulo" class="titulo"></div>
        <div id="hoja-horario" class="horario"></div>
        <div id="hoja-nota" class="nota"></div>
      </div>
    </div>
    <div id="hoja-sinopsis" class="sinopsis"></div>
    <div id="hoja-creditos" class="creditos"></div>
    <div id="hoja-sin-anuncios" class="sinanuncios"></div>
    <div class="g2" style="margin-top:12px">
      <button class="b" data-local="hoja-tele">📺 Ficha en la tele</button>
      <button class="b ok" data-local="hoja-accion" id="hoja-accion">Poner</button>
    </div>
    <button class="b" data-local="hoja-seguir" style="width:100%;margin-top:8px">⭐ Seguir este programa (cada vez que salga)</button>
  </div>
</div>
<div id="toast"></div>

<script>
(function () {
  var tituloActual = '';
  var fichaManual = false;
  var canalAnterior = '';
  var siguienteRec = null;
  var resultados = [];

  function $(id) { return document.getElementById(id); }

  function aviso(msg, error) {
    var t = $('toast');
    t.textContent = msg;
    t.className = error ? 'error' : '';
    t.style.display = 'block';
    clearTimeout(aviso.temporizador);
    aviso.temporizador = setTimeout(function () { t.style.display = 'none'; }, 2600);
  }

  function pedir(url) {
    return fetch(url, {cache: 'no-store'}).then(function (r) {
      return r.json().then(function (d) { d._http = r.status; return d; });
    });
  }

  function orden(cmd, extra) {
    var url = '/api/action?cmd=' + encodeURIComponent(cmd) + (extra || '');
    return pedir(url).then(function (d) {
      aviso(d.message || 'Hecho', d._http >= 400);
      setTimeout(estado, 700);
    }).catch(function () { aviso('No hay conexión con el hub', true); });
  }

  function pintarCreditos(caja, creditos) {
    caja.textContent = '';
    Object.keys(creditos || {}).forEach(function (k) {
      var fila = document.createElement('div');
      var b = document.createElement('b');
      b.textContent = k + ': ';
      fila.appendChild(b);
      fila.appendChild(document.createTextNode(creditos[k]));
      caja.appendChild(fila);
    });
  }

  function minutoDe(p) {
    var t = Date.now() / 1000;
    if (!p || !p.inicio_ts || !(p.inicio_ts <= t && t < p.fin_ts)) { return ''; }
    return 'minuto ' + (Math.floor((t - p.inicio_ts) / 60) + 1) + ' de ' +
      Math.max(1, Math.round((p.fin_ts - p.inicio_ts) / 60));
  }

  function pintarSinAnuncios(caja, lista) {
    caja.textContent = '';
    if (!lista || !lista.length) { return; }
    caja.appendChild(document.createTextNode('Sin anuncios en: ' + lista.map(function (p) { return p.nombre; }).join(', ')));
    var br = document.createElement('div');
    lista.forEach(function (p) {
      if (!p.app) { return; }
      var b = document.createElement('button');
      b.className = 'b mini';
      b.setAttribute('data-cmd', 'app_' + p.app);
      b.textContent = '▶ Abrir ' + p.app;
      br.appendChild(b);
    });
    caja.appendChild(br);
  }

  // ------------------------------------------------------------ ajustes
  function abrirAjustes() {
    pedir('/api/ajustes').then(function (d) {
      Array.prototype.forEach.call(document.querySelectorAll('[data-aj]'), function (el) {
        var k = el.getAttribute('data-aj'), v = d[k];
        if (el.type === 'checkbox') { el.checked = !!v; }
        else if (el.type === 'password') { el.value = ''; el.placeholder = v ? 'puesta (vacía = no cambiarla)' : 'sin poner'; }
        else { el.value = v === undefined || v === null ? '' : v; }
      });
      $('aj-mac').textContent = d.mac_detectada ? 'Detectada en la red: ' + d.mac_detectada : '';
      $('aj-url-avisos').textContent = 'Avisos desde Home Assistant (rest_command): ' + d.url_avisos;
      $('aj-panel').classList.remove('oculto');
      document.body.classList.add('sin-scroll');
    }).catch(function () { aviso('No hay conexión con el hub', true); });
  }

  function guardarAjustes() {
    var cambios = {};
    Array.prototype.forEach.call(document.querySelectorAll('[data-aj]'), function (el) {
      var k = el.getAttribute('data-aj');
      if (el.type === 'checkbox') { cambios[k] = el.checked; }
      else if (el.type === 'password') { if (el.value) { cambios[k] = el.value; } }
      else { cambios[k] = el.value; }
    });
    fetch('/api/ajustes', {method: 'POST', cache: 'no-store', body: JSON.stringify(cambios)})
      .then(function (r) { return r.json().then(function (d) { d._http = r.status; return d; }); })
      .then(function (d) { aviso(d.message || 'Hecho', d._http >= 400); if (d._http < 400) { estado(); } })
      .catch(function () { aviso('No hay conexión con el hub', true); });
  }

  function pintarFicha(f) {
    if (!f) { return; }
    $('titulo').textContent = f.title + (f.year ? ' (' + f.year + ')' : '');
    $('nota').textContent = f.rating || '';
    $('insignia').textContent = f.badge || '';
    if (f.synopsis) { $('sinopsis').textContent = f.synopsis; }
    var img = $('poster');
    if (f.poster_url) { img.src = f.poster_url; img.style.visibility = 'visible'; }
    else { img.removeAttribute('src'); img.style.visibility = 'hidden'; }
  }

  function ahora() {
    if (fichaManual) { return; }
    pedir('/api/ahora').then(function (d) {
      var e = d.epg || {};
      var a = e.actual;
      $('aviso-epg').textContent = e.aviso || '';
      if (!a) {
        $('titulo').textContent = 'Sin guía para ' + (e.canal || 'este canal');
        $('horario').textContent = ''; $('nota').textContent = ''; $('sinopsis').textContent = '';
        $('progreso').style.width = '0';
        pintarCreditos($('creditos'), null);
      } else {
        tituloActual = a.titulo_busqueda || a.titulo;
        $('sinopsis').textContent = a.descripcion || '';
        pintarFicha(d.ficha);
        $('titulo').textContent = a.titulo;
        $('horario').textContent = a.inicio + ' – ' + a.fin + (minutoDe(a) ? ' · ' + minutoDe(a) : '') +
          (a.categoria ? ' · ' + a.categoria : '');
        pintarCreditos($('creditos'), a.creditos);
        $('progreso').style.width = (a.progreso || 0) + '%';
      }
      var s = e.siguiente;
      $('despues').textContent = s ? 'Después: ' + s.titulo + ' (' + s.inicio + ')' : '';
      $('btn-principio').classList.toggle('oculto', !(a && Date.now() / 1000 - a.inicio_ts > 180));
      pintarSinAnuncios($('sin-anuncios'), d.sin_anuncios);
      siguienteRec = s && s.inicio_ts && e.canal_epg ?
        {canal: e.canal_epg, nombre: e.canal_epg, inicio_ts: s.inicio_ts, numero: e.numero || ''} : null;
      $('btn-recordar-sig').classList.toggle('oculto', !siguienteRec);
    }).catch(function () {});
  }

  var SEMANA = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

  function diasDesdeHoy(ts) {
    var d = new Date(ts * 1000), hoy = new Date();
    return Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) -
                       new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate())) / 86400000);
  }

  function dia(ts) {
    var n = diasDesdeHoy(ts);
    return n === 0 ? '' : (n === 1 ? 'mañana ' : (n === -1 ? 'ayer ' : SEMANA[new Date(ts * 1000).getDay()] + ' '));
  }

  function nombreDia(ts) {
    var n = diasDesdeHoy(ts), d = new Date(ts * 1000);
    var base = n === 0 ? 'Hoy' : (n === 1 ? 'Mañana' : (n === -1 ? 'Ayer' : ''));
    return (base ? base + ' · ' : '') + SEMANA[d.getDay()] + ' ' + d.getDate();
  }

  function linea(texto, boton, clase) {
    var f = document.createElement('div');
    f.className = 'linea' + (clase ? ' ' + clase : '');
    var t = document.createElement('span');
    t.textContent = texto;
    f.appendChild(t);
    if (boton) { f.appendChild(boton); }
    return f;
  }

  function boton(texto, local, atributos) {
    var b = document.createElement('button');
    b.className = 'b mini';
    b.textContent = texto;
    b.setAttribute('data-local', local);
    Object.keys(atributos).forEach(function (k) { b.setAttribute(k, atributos[k]); });
    return b;
  }

  function recordar(r) {
    if (!r) { return; }
    var accion = $('rec-accion').value;
    var numero = r.numero || '';
    if (accion !== 'whatsapp' && !numero) {
      numero = (window.prompt('¿Qué número tiene «' + r.nombre + '» en tu tele?') || '').trim();
      if (!/^[0-9]{1,4}$/.test(numero)) { aviso('Hace falta el número del canal en tu tele', true); return; }
    }
    orden('recordar', '&canal=' + encodeURIComponent(r.canal) + '&inicio=' + encodeURIComponent(r.inicio_ts) +
          '&accion=' + accion + (numero ? '&numero=' + numero : '')).then(listaRecordatorios);
  }

  function buscarGuia() {
    var q = $('guia-q').value.trim();
    if (q.length < 2) { return; }
    var caja = $('guia-res');
    caja.textContent = '';
    caja.appendChild(linea('Buscando...', null, 'hecho'));
    pedir('/api/guia?q=' + encodeURIComponent(q)).then(function (d) {
      resultados = d.resultados || [];
      caja.textContent = '';
      if (!resultados.length) { caja.appendChild(linea(d.aviso || 'No sale en la guía', null, 'hecho')); return; }
      resultados.forEach(function (r, i) {
        caja.appendChild(linea(dia(r.inicio_ts) + r.inicio + ' · ' + r.titulo + ' (' + r.nombre +
          (r.numero ? ', canal ' + r.numero : '') + ')', boton('⏰', 'recordar', {'data-i': i})));
      });
    }).catch(function () { caja.textContent = ''; aviso('No hay conexión con el hub', true); });
  }

  var filasParrilla = [];
  var parrillaEntera = false;
  var PARRILLA_CORTA = 8;

  function parrilla() {
    pedir('/api/parrilla').then(function (d) {
      filasParrilla = d.canales || [];
      $('parrilla-aviso').textContent = d.aviso || '';
      pintarParrilla();
    }).catch(function () {});
  }

  function pintarParrilla() {
    var caja = $('parrilla');
    caja.textContent = '';
    (parrillaEntera ? filasParrilla : filasParrilla.slice(0, PARRILLA_CORTA)).forEach(function (f, i) {
      var fila = document.createElement('div');
      fila.className = 'canal' + (f.viendo ? ' viendo' : '');
      var num = document.createElement('div');
      num.className = 'num' + (f.numero ? '' : ' sin');
      num.textContent = f.numero || '–';
      if (!f.numero) { num.title = 'Aún no sé su número en tu tele: te lo pregunto al pulsar «Poner»'; }
      var prog = document.createElement('div');
      prog.className = 'prog';
      var nombre = document.createElement('b');
      nombre.textContent = f.canal + (f.viendo ? ' · en la tele' : '');
      prog.appendChild(nombre);
      var a = f.ahora, s = f.despues;
      var ahoraTxt = document.createElement('div');
      ahoraTxt.className = 'ahora' + (a ? ' toca' : '');
      ahoraTxt.textContent = a ? a.inicio + ' ' + a.titulo : 'Sin datos de ahora';
      if (a) { ahoraTxt.setAttribute('data-local', 'ficha'); ahoraTxt.setAttribute('data-i', i); ahoraTxt.setAttribute('data-cual', 'ahora'); }
      prog.appendChild(ahoraTxt);
      if (a) {
        var barra = document.createElement('div');
        barra.className = 'barra';
        var lleno = document.createElement('div');
        lleno.style.width = (a.progreso || 0) + '%';
        barra.appendChild(lleno);
        prog.appendChild(barra);
      }
      if (s) {
        var luego = document.createElement('div');
        luego.className = 'luego toca';
        luego.textContent = 'Después ' + s.inicio + ' ' + s.titulo;
        luego.setAttribute('data-local', 'ficha');
        luego.setAttribute('data-i', i);
        luego.setAttribute('data-cual', 'despues');
        prog.appendChild(luego);
      }
      fila.appendChild(num);
      fila.appendChild(prog);
      fila.appendChild(boton('Poner', 'poner', {'data-i': i}));
      caja.appendChild(fila);
    });
    var mas = $('parrilla-mas');
    mas.classList.toggle('oculto', filasParrilla.length <= PARRILLA_CORTA);
    mas.textContent = parrillaEntera ? 'Ver menos' : 'Ver todos los canales (' + filasParrilla.length + ')';
  }

  function poner(f) {
    if (!f) { return; }
    var numero = f.numero || '';
    if (!numero) {
      numero = (window.prompt('¿Qué número tiene «' + f.canal + '» en tu tele?') || '').trim();
      if (!/^[0-9]{1,4}$/.test(numero)) { aviso('Hace falta el número del canal en tu tele', true); return; }
    }
    orden('poner_canal', '&canal=' + encodeURIComponent(f.canal) + (f.numero ? '' : '&numero=' + numero)).then(parrilla);
  }

  var hojaActual = null;

  function pintarHoja(p, ficha) {
    var titulo = (ficha && ficha.title) || p.titulo;
    $('hoja-titulo').textContent = titulo + (ficha && ficha.year ? ' (' + ficha.year + ')' : '');
    $('hoja-horario').textContent = dia(p.inicio_ts) + p.inicio + ' – ' + p.fin +
      (minutoDe(p) ? ' · ' + minutoDe(p) : '') + (p.categoria ? ' · ' + p.categoria : '');
    pintarCreditos($('hoja-creditos'), p.creditos);
    $('hoja-nota').textContent = (ficha && ficha.rating) || '';
    $('hoja-insignia').textContent = (ficha && ficha.badge) || '';
    $('hoja-sinopsis').textContent = (ficha && ficha.synopsis) || p.descripcion || 'Sin sinopsis en la guía.';
    var img = $('hoja-poster'), src = (ficha && ficha.poster_url) || p.imagen;
    if (src) { img.src = src; img.style.visibility = 'visible'; }
    else { img.removeAttribute('src'); img.style.visibility = 'hidden'; }
  }

  function abrirFicha(f, p, cual) {
    if (!f || !p) { return; }
    hojaActual = {fila: f, prog: p, cual: cual};
    $('hoja-canal').textContent = (cual === 'ahora' ? 'AHORA EN ' : (cual === 'pasado' ? 'YA EMITIDO EN ' : 'DESPUÉS EN ')) +
      f.canal.toUpperCase();
    $('hoja-accion').textContent = cual === 'ahora' ? '▶ Poner' : '⏰ Recordar';
    $('hoja-accion').classList.toggle('oculto', cual === 'pasado');
    pintarHoja(p, null);
    pintarSinAnuncios($('hoja-sin-anuncios'), null);
    $('hoja-fondo').classList.add('abierta');
    var pedida = hojaActual;
    pedir('/api/ficha?canal=' + encodeURIComponent(f.canal) + '&inicio=' + encodeURIComponent(p.inicio_ts))
      .then(function (d) {
        if (hojaActual !== pedida) { return; }
        if (d.ficha) { pintarHoja(p, d.ficha); }
        pintarSinAnuncios($('hoja-sin-anuncios'), d.sin_anuncios);
      })
      .catch(function () {});
  }

  function cerrarHoja() {
    hojaActual = null;
    $('hoja-fondo').classList.remove('abierta');
  }

  // ------------------------------------------------------------ guía completa
  var guiaCanales = [], guiaCanal = '', guiaNumero = '', guiaProgramas = [];

  function abrirGuia() {
    $('guia-panel').classList.remove('oculto');
    document.body.classList.add('sin-scroll');
    pedir('/api/guia_canales').then(function (d) {
      guiaCanales = d.canales || [];
      pintarCanalesGuia();
      if (!guiaCanales.length) { vacioGuia(d.aviso || 'La guía aún no se ha descargado'); return; }
      verCanal(guiaCanal || d.viendo || guiaCanales[0].canal);
    }).catch(function () { aviso('No hay conexión con el hub', true); });
  }

  function cerrarGuia() {
    $('guia-panel').classList.add('oculto');
    document.body.classList.remove('sin-scroll');
  }

  function vacioGuia(texto) {
    var lista = $('gp-lista');
    lista.textContent = '';
    var v = document.createElement('div');
    v.className = 'gp-vacio';
    v.textContent = texto;
    lista.appendChild(v);
  }

  function pintarCanalesGuia() {
    var chips = $('gp-chips'), sel = $('gp-canal'), grupos = {};
    var NOMBRES = {tuyos: 'Tus canales', tdt: 'TDT nacional', otros: 'Más canales de la guía'};
    chips.textContent = '';
    sel.textContent = '';
    guiaCanales.forEach(function (c) {
      var texto = (c.numero ? c.numero + ' · ' : '') + c.canal;
      if (c.grupo !== 'otros') {
        var b = document.createElement('button');
        b.className = 'gp-chip';
        b.textContent = texto;
        b.setAttribute('data-local', 'gp-canal');
        b.setAttribute('data-canal', c.canal);
        chips.appendChild(b);
      }
      if (!grupos[c.grupo]) {
        grupos[c.grupo] = document.createElement('optgroup');
        grupos[c.grupo].label = NOMBRES[c.grupo] || c.grupo;
        sel.appendChild(grupos[c.grupo]);
      }
      var o = document.createElement('option');
      o.value = c.canal;
      o.textContent = texto;
      grupos[c.grupo].appendChild(o);
    });
  }

  function verCanal(canal) {
    if (!canal) { return; }
    guiaCanal = canal;
    $('gp-canal').value = canal;
    Array.prototype.forEach.call(document.querySelectorAll('.gp-chip'), function (b) {
      b.classList.toggle('activo', b.getAttribute('data-canal') === canal);
    });
    var activo = document.querySelector('.gp-chip.activo');
    if (activo && activo.scrollIntoView) { activo.scrollIntoView({block: 'nearest', inline: 'center'}); }
    $('gp-poner').classList.add('oculto');
    vacioGuia('Cargando la guía de ' + canal + '…');
    pedir('/api/guia_canal?canal=' + encodeURIComponent(canal)).then(function (d) {
      if (guiaCanal !== canal) { return; }
      guiaProgramas = d.programas || [];
      guiaNumero = d.numero || '';
      pintarGuia(d.aviso);
    }).catch(function () { vacioGuia('No hay conexión con el hub'); });
  }

  function pintarGuia(avisoGuia) {
    var lista = $('gp-lista'), diaAnterior = '', enEmision = null;
    var poner = $('gp-poner');
    poner.textContent = '▶ Poner ' + guiaCanal + (guiaNumero ? ' (canal ' + guiaNumero + ')' : '');
    poner.classList.remove('oculto');
    lista.textContent = '';
    if (!guiaProgramas.length) { vacioGuia(avisoGuia || 'Sin programas'); return; }
    guiaProgramas.forEach(function (p, i) {
      var nd = nombreDia(p.inicio_ts);
      if (nd !== diaAnterior) {
        diaAnterior = nd;
        var cab = document.createElement('div');
        cab.className = 'gp-dia';
        cab.textContent = nd;
        lista.appendChild(cab);
      }
      var fila = document.createElement('div');
      fila.className = 'gp-prog ' + p.estado;
      fila.setAttribute('data-local', 'gp-ficha');
      fila.setAttribute('data-i', i);
      var hora = document.createElement('div');
      hora.className = 'gp-hora';
      hora.textContent = p.inicio;
      var info = document.createElement('div');
      info.className = 'gp-info';
      var t = document.createElement('div');
      t.className = 'gp-t';
      t.textContent = p.titulo;
      var c = document.createElement('div');
      c.className = 'gp-c';
      c.textContent = (p.estado === 'ahora' ? 'AHORA · ' : '') + 'hasta las ' + p.fin + (p.categoria ? ' · ' + p.categoria : '');
      info.appendChild(t);
      info.appendChild(c);
      if (p.estado === 'ahora') {
        var barra = document.createElement('div');
        barra.className = 'barra';
        var lleno = document.createElement('div');
        lleno.style.width = (p.progreso || 0) + '%';
        barra.appendChild(lleno);
        info.appendChild(barra);
        enEmision = fila;
      }
      fila.appendChild(hora);
      fila.appendChild(info);
      lista.appendChild(fila);
    });
    if (enEmision && enEmision.scrollIntoView) { enEmision.scrollIntoView({block: 'center'}); }
    else { $('gp-cuerpo').scrollTop = 0; }
  }

  function mensaje() {
    var t = $('mensaje').value.trim();
    if (!t) { return; }
    pedir('/api/action?cmd=mensaje_tv&texto=' + encodeURIComponent(t)).then(function (d) {
      aviso(d.message || 'Hecho', d._http >= 400);
      if (d._http < 400) { $('mensaje').value = ''; }
    }).catch(function () { aviso('No hay conexión con el hub', true); });
  }

  var ICONOS = {tele: '📺', whatsapp: '💬', ambos: '📺💬'};

  function listaRecordatorios() {
    pedir('/api/recordatorios').then(function (d) {
      var caja = $('rec-lista');
      caja.textContent = '';
      (d.pendientes || []).forEach(function (r) {
        caja.appendChild(linea((ICONOS[r.accion] || '') + ' ' + dia(r.inicio_ts) + r.hora + ' · ' + r.titulo +
          ' (' + r.nombre + (r.numero ? ', canal ' + r.numero : '') + ')', boton('✕', 'olvidar', {'data-id': r.id})));
      });
      (d.hechos || []).forEach(function (r) {
        caja.appendChild(linea('✔ ' + r.hora + ' · ' + r.titulo + ': ' + r.resultado, null, 'hecho'));
      });
      $('rec-aviso').textContent = (d.pendientes || []).length && !d.servicio ?
        'El silenciador automático no está en marcha: los recordatorios no saltarán.' : '';
    }).catch(function () {});
  }

  function estado() {
    pedir('/api/status').then(function (d) {
      $('chip-canal').textContent = 'Canal: ' + d.canal;
      var tv = $('chip-tv');
      if (d.conexion === 'device') {
        tv.textContent = d.encendida === false ? 'TV: en reposo' : 'TV: conectada';
        tv.className = 'chip bien';
      } else if (d.conexion === 'unauthorized') {
        tv.textContent = 'TV: acepta el aviso en la pantalla'; tv.className = 'chip mal';
      } else {
        tv.textContent = 'TV: sin conexión'; tv.className = 'chip mal';
      }
      var a = d.auto;
      var texto = !a.servicio ? 'servicio parado' : (a.pausado ? 'en pausa' : 'activo');
      $('chip-auto').textContent = 'Silenciador: ' + texto;
      $('chip-auto').className = 'chip ' + (a.servicio && !a.pausado ? 'bien' : 'mal');
      $('auto-estado').textContent = a.silenciada ? 'silenciando (' + a.quedan + ' s)' : texto;
      $('auto-cortes').textContent = a.cortes_hoy + (a.minutos_hoy ? ' (' + a.minutos_hoy + ' min)' : '');
      $('auto-ultimo').textContent = a.ultimo_corte ? a.ultimo_corte.hora + ' en ' + a.ultimo_corte.canal : '—';
      var v = d.vuelta || {};
      var fuera = v.estado === 'fuera';
      $('vuelta').classList.toggle('oculto', !fuera);
      if (fuera) {
        var m = Math.floor(v.quedan / 60), s = v.quedan % 60;
        $('vuelta-texto').textContent = 'a ' + v.origen + ' en ' + m + ':' + (s < 10 ? '0' : '') + s;
      }
      $('btn-pausa').classList.toggle('oculto', a.pausado);
      $('btn-reanudar').classList.toggle('oculto', !a.pausado);
      $('btn-devolver').style.display = a.silenciada ? 'block' : 'none';
      $('btn-publi').textContent = a.silenciada ? '🔇 SILENCIADA · quedan ' + a.quedan + ' s' : '🔇 SILENCIAR ANUNCIOS (' + a.mute_segundos + ' s)';
      $('btn-whatsapp').classList.toggle('oculto', !d.whatsapp);
      Array.prototype.forEach.call(document.querySelectorAll('.solo-wa'), function (o) {
        o.hidden = !d.whatsapp; o.disabled = !d.whatsapp;
      });
      if (!d.whatsapp && $('rec-accion').value !== 'tele') { $('rec-accion').value = 'tele'; }
      var av = d.avisos_tv || {};
      var MODOS = {app: 'listos: en el centro y grandes', tvoverlay: 'en una esquina (TvOverlay): pulsa «Preparar avisos»'};
      $('avisos-estado').textContent = !av.activo ? 'desactivados' : (MODOS[av.modo] || 'sin preparar: pulsa «Preparar avisos»');
      $('avisos-estado').style.color = av.activo && av.modo !== 'app' ? '#fca5a5' : '';
      var c = d.casa || {};
      $('card-casa').classList.toggle('oculto', !(c.ha || c.ambilight));
      $('btn-cine-on').classList.toggle('oculto', !!c.cine);
      $('btn-cine-off').classList.toggle('oculto', !c.cine);
      $('pi-tdt').textContent = (c.sintonizador || []).length ? 'conectado (' + c.sintonizador.join(', ') + ')' : 'no conectado';
      var cajaSeg = $('seguidos');
      cajaSeg.textContent = '';
      (d.seguidos || []).forEach(function (s) {
        cajaSeg.appendChild(linea('⭐ Sigues: ' + s.titulo + ' (' + (ICONOS[s.accion] || '') + ')',
                                  boton('✕', 'dejar-seguir', {'data-id': s.id})));
      });
      var sg = d.senal_guia || {};
      $('guia-senal').textContent = (sg.silencia ? 'silencia' : 'solo se apunta') + ' · ' + (sg.coinciden || 0) +
        ' de ' + (sg.botones || 0) + ' veces que pulsaste Silenciar';
      $('btn-guia-on').classList.toggle('oculto', !!sg.silencia);
      $('btn-guia-off').classList.toggle('oculto', !sg.silencia);
      var cajaSg = $('guia-senales');
      cajaSg.textContent = '';
      (sg.ultimas || []).forEach(function (s) {
        cajaSg.appendChild(linea(s.hora + ' · ' + s.canal + (s.con_boton ? ' · ✔ pulsaste Silenciar' : ''), null,
                                 s.con_boton ? '' : 'hecho'));
      });
      $('nocturno').textContent = d.apagado_nocturno ? 'Apagado nocturno automático a las ' + d.apagado_nocturno : '';
      var p = d.pi || {};
      $('pi-temp').textContent = p.temperatura !== null && p.temperatura !== undefined ? p.temperatura + ' °C' : '—';
      $('pi-alim').textContent = p.alimentacion_ok === null || p.alimentacion_ok === undefined ? '—' :
        (p.alimentacion_ok ? 'correcta' : p.alimentacion.join(', '));
      $('pi-alim').style.color = p.alimentacion_ok === false ? '#fca5a5' : '';
      $('pi-carga').textContent = (p.carga !== null && p.carga !== undefined ? p.carga : '—') + ' / ' + (p.ram_libre_mb ? p.ram_libre_mb + ' MB' : '—');
      $('pi-up').textContent = p.encendida_horas !== null && p.encendida_horas !== undefined ? p.encendida_horas + ' h' : '—';
      if (d.canal !== canalAnterior) { canalAnterior = d.canal; fichaManual = false; ahora(); parrilla(); }
    }).catch(function () {
      $('chip-tv').textContent = 'Hub sin respuesta'; $('chip-tv').className = 'chip mal';
    });
  }

  function apps() {
    pedir('/api/apps').then(function (d) {
      var caja = $('apps');
      caja.textContent = '';
      (d.apps || []).forEach(function (nombre) {
        var b = document.createElement('button');
        b.className = 'b app';
        b.setAttribute('data-cmd', 'app_' + nombre);
        b.textContent = nombre;
        caja.appendChild(b);
      });
    }).catch(function () {});
  }

  function buscar() {
    var v = $('buscar').value.trim();
    if (!v) { return; }
    fichaManual = true;
    tituloActual = v;
    $('horario').textContent = ''; $('progreso').style.width = '0'; $('despues').textContent = '';
    $('sinopsis').textContent = 'Buscando...';
    pedir('/api/movie_info?title=' + encodeURIComponent(v)).then(pintarFicha).catch(function () {});
  }

  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-cmd],[data-local]');
    if (!b) { return; }
    var local = b.getAttribute('data-local');
    if (local === 'buscar') { buscar(); return; }
    if (local === 'guia') { buscarGuia(); return; }
    if (local === 'recordar') { recordar(resultados[+b.getAttribute('data-i')]); return; }
    if (local === 'recordar-sig') { recordar(siguienteRec); return; }
    if (local === 'poner') { poner((parrillaEntera ? filasParrilla : filasParrilla.slice(0, PARRILLA_CORTA))[+b.getAttribute('data-i')]); return; }
    if (local === 'parrilla-mas') { parrillaEntera = !parrillaEntera; pintarParrilla(); return; }
    if (local === 'ficha') {
      var fp = (parrillaEntera ? filasParrilla : filasParrilla.slice(0, PARRILLA_CORTA))[+b.getAttribute('data-i')];
      abrirFicha(fp, fp && fp[b.getAttribute('data-cual')], b.getAttribute('data-cual'));
      return;
    }
    if (local === 'aj-abrir') { abrirAjustes(); return; }
    if (local === 'aj-cerrar') { $('aj-panel').classList.add('oculto'); document.body.classList.remove('sin-scroll'); return; }
    if (local === 'aj-guardar') { guardarAjustes(); return; }
    if (local === 'usar-movil') { orden('usar_este_movil').then(abrirAjustes); return; }
    if (local === 'dejar-seguir') { orden('dejar_seguir', '&id=' + encodeURIComponent(b.getAttribute('data-id'))); return; }
    if (local === 'hoja-seguir' && hojaActual) {
      orden('seguir', '&titulo=' + encodeURIComponent(hojaActual.prog.titulo_busqueda || hojaActual.prog.titulo) +
            '&canal=' + encodeURIComponent(hojaActual.fila.canal) + '&accion=' + $('rec-accion').value)
        .then(listaRecordatorios);
      return;
    }
    if (local === 'guia-abrir') { abrirGuia(); return; }
    if (local === 'guia-cerrar') { cerrarGuia(); return; }
    if (local === 'gp-canal') { verCanal(b.getAttribute('data-canal')); return; }
    if (local === 'gp-poner') { poner({canal: guiaCanal, numero: guiaNumero}); return; }
    if (local === 'gp-ficha') {
      var gp = guiaProgramas[+b.getAttribute('data-i')];
      if (gp) { abrirFicha({canal: guiaCanal, numero: guiaNumero}, gp, gp.estado); }
      return;
    }
    if (local === 'hoja-fondo') { if (e.target === b) { cerrarHoja(); } return; }
    if (local === 'hoja-cerrar') { cerrarHoja(); return; }
    if (local === 'hoja-tele' && hojaActual) {
      orden('project_banner', '&canal=' + encodeURIComponent(hojaActual.fila.canal) +
            '&inicio=' + encodeURIComponent(hojaActual.prog.inicio_ts));
      return;
    }
    if (local === 'hoja-accion' && hojaActual) {
      var h = hojaActual;
      cerrarHoja();
      if (h.cual === 'ahora') { poner(h.fila); }
      else { recordar({canal: h.fila.canal, nombre: h.fila.canal, inicio_ts: h.prog.inicio_ts, numero: h.fila.numero}); }
      return;
    }
    if (local === 'mensaje') { mensaje(); return; }
    if (local === 'olvidar') {
      orden('olvidar', '&id=' + encodeURIComponent(b.getAttribute('data-id'))).then(listaRecordatorios);
      return;
    }
    if (local === 'texto') {
      var t = $('texto').value;
      if (t) { orden('texto', '&text=' + encodeURIComponent(t)); $('texto').value = ''; }
      return;
    }
    var cmd = b.getAttribute('data-cmd');
    if (cmd === 'apagar' && !confirm('¿Apagar la televisión?')) { return; }
    if (cmd === 'project_banner') {
      orden(cmd, fichaManual ? '&title=' + encodeURIComponent(tituloActual) : '');
      return;
    }
    orden(cmd);
  });

  $('gp-canal').addEventListener('change', function (e) { verCanal(e.target.value); });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') { return; }
    if (e.target.id === 'buscar') { buscar(); }
    if (e.target.id === 'guia-q') { buscarGuia(); }
    if (e.target.id === 'mensaje') { mensaje(); }
    if (e.target.id === 'texto' && e.target.value) {
      orden('texto', '&text=' + encodeURIComponent(e.target.value)); e.target.value = '';
    }
  });

  estado();
  apps();
  listaRecordatorios();
  setInterval(estado, 5000);
  setInterval(ahora, 60000);
  setInterval(listaRecordatorios, 30000);
  setInterval(parrilla, 120000);
})();
</script>
</body>
</html>
"""


class RemoteHandler(BaseHTTPRequestHandler):
    server_version = "PanasonicTVHub/2.0"

    def log_message(self, formato, *args):  # silencio en el registro salvo errores
        return

    def _cabeceras_sin_cache(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def _html(self, html):
        cuerpo = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cabeceras_sin_cache()
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, datos, codigo=200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cabeceras_sin_cache()
        self.end_headers()
        self.wfile.write(cuerpo)

    def _instalador_termux(self):
        """El instalador del hub para un móvil con Termux, con la IP de esta tele ya puesta. Así, en el móvil
        basta con escribir «curl -s <IP del PC>:8080/termux | bash» (sin copiar la dirección larga de GitHub)."""
        try:
            with open(os.path.join(BASE, "termux", "instalar.sh"), encoding="utf-8") as f:
                guion = f.read()
        except OSError:
            self._json({"status": "error", "message": "No existe"}, 404)
            return
        ip = re.sub(r"[^0-9A-Za-z.:-]", "", TV_IP)
        cuerpo = guion.replace('TV_IP="${1:-}"', f'TV_IP="${{1:-{ip}}}"').encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cabeceras_sin_cache()
        self.end_headers()
        self.wfile.write(cuerpo)

    def _fichero(self, ruta, tipo):
        try:
            with open(ruta, "rb") as f:
                cuerpo = f.read()
        except OSError:
            self._json({"status": "error", "message": "No existe"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self._cabeceras_sin_cache()
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        try:
            # Se lee el cuerpo ANTES de contestar: si se contesta con él sin leer, Windows corta la conexión
            largo = min(int(self.headers.get("Content-Length") or 0), 20000)
            leido = self.rfile.read(largo) if largo > 0 else b""
            if self._rechazar(url):
                return
            if orden_desde_otra_web(self.headers):
                self._json({"status": "error", "message": "Las órdenes solo se aceptan desde la página del mando"}, 403)
                return
            if url.path != "/api/ajustes":
                self._json({"status": "error", "message": "No existe"}, 404)
                return
            try:
                cambios = json.loads(leido.decode("utf-8") or "{}")
                if not isinstance(cambios, dict):
                    raise ValueError("Se esperaba un objeto")
                ajustes.guardar(cambios)
            except ValueError as e:
                self._json({"status": "error", "message": str(e)}, 400)
                return
            self._json({"status": "ok", "message": "Ajustes guardados", "ajustes": ajustes_publicos()})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            print(f"[Web] Error en {url.path}: {e}", flush=True)
            try:
                self._json({"status": "error", "message": f"Error interno: {e}"}, 500)
            except OSError:
                pass

    def _rechazar(self, url) -> bool:
        """True si la petición no viene de casa (y ya se ha contestado con un 403)."""
        if not (cliente_permitido(self.client_address[0]) and host_permitido(self.headers.get("Host"))):
            motivo = "Solo se puede usar desde la red de casa"
        elif url.path == "/api/action" and orden_desde_otra_web(self.headers):
            motivo = "Las órdenes solo se aceptan desde la página del mando"
        else:
            return False
        print(f"[Web] Rechazada {self.client_address[0]} ({self.headers.get('Host')}) {url.path}: {motivo}", flush=True)
        self._json({"status": "error", "message": motivo}, 403)
        return True

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if self._rechazar(url):
                return
            if url.path in ("/", "/index.html"):
                self._html(HTML_MOBILE_PAGE)
            elif url.path == "/tv_banner":
                self._html(TV_BANNER_HTML)
            elif url.path == "/api/status":
                self._json(estado_completo())
            elif url.path == "/api/ahora":
                self._json(ahora_en_emision())
            elif url.path == "/api/apps":
                self._json({"apps": en_cache("apps", tv.apps_instaladas, 300)})
            elif url.path == "/api/movie_info":
                self._json(MediaInfoService.buscar_info_pelicula(qs.get("title", [""])[0]))
            elif url.path == "/api/guia":
                self._json(buscar_en_guia(qs.get("q", [""])[0]))
            elif url.path == "/api/recordatorios":
                self._json(lista_recordatorios())
            elif url.path == "/api/parrilla":
                self._json(parrilla())
            elif url.path == "/api/ficha":
                self._json(ficha_programa(qs))
            elif url.path == "/privacidad":
                self._html(HTML_PRIVACIDAD)
            elif url.path == "/termux":
                self._instalador_termux()
            elif url.path == "/api/privacidad":
                self._json(privacidad())
            elif url.path == "/api/ajustes":
                self._json(ajustes_publicos())
            elif url.path == "/api/aviso_casa":
                codigo, msg = aviso_casa(qs)
                self._json({"status": "ok" if codigo < 400 else "error", "message": msg}, codigo)
            elif url.path == "/camara.jpg":
                self._fichero(estado.ruta("camara.jpg"), "image/jpeg")
            elif url.path == "/api/action" and qs.get("cmd", [""])[0] == "usar_este_movil":
                try:
                    ajustes.guardar({"salir_ip": self.client_address[0]})
                    self._json({"status": "ok", "message": f"Móvil apuntado: {self.client_address[0]}"})
                except ValueError as e:
                    self._json({"status": "error", "message": str(e)}, 400)
            elif url.path == "/api/guia_canales":
                self._json(guia_canales())
            elif url.path == "/api/guia_canal":
                self._json(guia_de_canal(qs))
            elif url.path == "/api/action":
                cmd = qs.get("cmd", [""])[0]
                codigo, msg = ejecutar_accion(cmd, qs)
                self._json({"status": "ok" if codigo < 400 else "error", "message": msg}, codigo)
            else:
                self._json({"status": "error", "message": "No existe"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            print(f"[Web] Error en {url.path}: {e}", flush=True)
            try:
                self._json({"status": "error", "message": f"Error interno: {e}"}, 500)
            except OSError:
                pass


class ServidorConHilos(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"


def main():
    tv.connect()
    threading.Thread(target=hilo_epg, daemon=True).start()
    server = ServidorConHilos(("0.0.0.0", PORT), RemoteHandler)
    print(f"[Smart Hub] Mando web en http://{LOCAL_IP}:{PORT}  (TV {TV_IP})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor web detenido.")


if __name__ == "__main__":
    main()
