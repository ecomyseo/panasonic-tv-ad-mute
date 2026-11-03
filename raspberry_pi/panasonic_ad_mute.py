#!/usr/bin/env python3
"""
Panasonic Google TV Ad-Mute Daemon (Raspberry Pi Zero 2 W / Linux)

- Escucha el logcat de la TV por ADB y silencia la publicidad al ver un marcador
  HbbTV; devuelve el sonido al cumplirse MUTE_DURATION (el temporizador hace de vigilante).
- Anota el canal que se está viendo (MtkTvChannelList_jni) para el mando web.
- Atiende órdenes del mando web (silenciar / restaurar) y respeta la pausa.
- Vuelta al canal tras los anuncios, con avisos en el centro de la pantalla (app «TV Hub Avisos»).
- Recordatorios de la guía: al empezar el programa pone su canal o manda un WhatsApp.
- Apagado nocturno opcional (APAGADO_NOCTURNO=HH:MM).
"""

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "core"))

import avisos_tv  # noqa: E402
import config  # noqa: E402
import estado  # noqa: E402
import recordatorios  # noqa: E402
import ajustes  # noqa: E402
import dns_hub  # noqa: E402
import casa as casa_mod  # noqa: E402
import ficha_tv  # noqa: E402
import pantalla_tv  # noqa: E402
import presencia  # noqa: E402
import rutinas  # noqa: E402
import seguir  # noqa: E402
import senal_guia  # noqa: E402
import vuelta as vuelta_mod  # noqa: E402
import whatsapp_privado  # noqa: E402
from epg import GuiaEPG  # noqa: E402
from media_info import MediaInfoService  # noqa: E402
from tv_manager import PAQUETE_TDT, SIN_VENTANA, PanasonicTVManager  # noqa: E402

CFG = config.cargar()
TV_IP = CFG["TV_IP"]
MUTE_DURATION = config.entero(CFG, "MUTE_DURATION", 150)
COOLDOWN_SECONDS = config.entero(CFG, "COOLDOWN_SECONDS", 30)
# Medido en la TV el 2026-11-02: estas dos líneas salen cada 30 s exactos y al cambiar de canal, con o
# sin anuncios. Usadas como marcador, la TV pasaría casi todo el tiempo silenciada.
PATRONES_FALSOS = ("exchangeType==28", "getHBBTVBannerControl")
PATRONES = [p for p in config.lista(CFG, "AD_PATTERNS") if p not in PATRONES_FALSOS]
DESCARTADOS = [p for p in config.lista(CFG, "AD_PATTERNS") if p in PATRONES_FALSOS]
PATRONES_FIN = config.lista(CFG, "AD_END_PATTERNS")
ETIQUETAS = config.lista(CFG, "LOGCAT_TAGS")
if not any(e.startswith("MtkTvBannerBase") for e in ETIQUETAS):
    ETIQUETAS.append("MtkTvBannerBase:D")  # rótulo del canal: de ahí sale su número
if not any(e.startswith("MtkTvEvent_jni") for e in ETIQUETAS):
    ETIQUETAS.append("MtkTvEvent_jni:D")  # novedades de la guía del canal (posible señal de los anuncios)
if not any(e.startswith("MtkTvAvMode_jni") for e in ETIQUETAS):
    ETIQUETAS.append("MtkTvAvMode_jni:D")  # brillo de la imagen (fotogramas negros entre anuncios)
_RE_LUMA = re.compile(r"ui2_avg_pixel_luma = (\d+)")
if not any(e.startswith("[GLUE][IR]u8KeyCode") for e in ETIQUETAS):
    ETIQUETAS.append("[GLUE][IR]u8KeyCode:W")  # las teclas del mando, en el registro del núcleo (botón de la ficha)
GUIA_SILENCIA = CFG.get("GUIA_SILENCIA", "0").strip() == "1"
DNS_ACTIVO = CFG.get("DNS_ACTIVO", "0").strip() == "1"
# Tecla del mando de verdad. Medido el 3/11/2026: el amarillo NO llega a la TDT (no sale en su KeyHandler), pero
# toda tecla del mando sale en el registro del NÚCLEO (logcat -b kernel) con su código de Linux:
#   W/[GLUE][IR]u8KeyCode(  651): 0x0190 , u8KeyState: 0x0   (0x0 = pulsada, 0x2 = soltada)
# Las que manda el hub por ADB no pasan por el infrarrojo y no salen ahí.
_RE_TECLA = re.compile(r"u8KeyCode\(\s*\d+\):\s*0x([0-9a-fA-F]+)\s*,\s*u8KeyState:\s*0x([0-9a-fA-F]+)")
BOTONES_FICHA = {"amarillo": (0x190, 1), "verde": (0x18F, 1), "info_doble": (0x166, 2)}
BUFFERS_LOGCAT = ["-b", "main", "-b", "system", "-b", "kernel"]
# Lo que de verdad usa el servicio. Medido el 3/11/2026: con las etiquetas de arriba la tele escribe ~357 líneas por
# segundo y solo ~7 sirven (casi todo es MtkTvAvMode_jni y MtkTvChannelList_jni). Se filtran EN LA TELE con
# «grep --line-buffered -F», así por la red y por Python solo pasa lo útil (en un móvil, menos batería y menos luz).
LINEAS_UTILES = ("Current channel", "getChannelNumber=", "getChannelName=", "_event_nfy_fct callback_type=4",
                 "avg_pixel_luma", "u8KeyCode")
FILTRAR_EN_TV = CFG.get("LOGCAT_FILTRO_TV", "1").strip() != "0"
TECLAS_VOLUMEN = (0x71, 0x72, 0x73)   # silencio, bajar y subir volumen del mando (registro del núcleo)
FICHA_AL_CAMBIAR = CFG.get("FICHA_AL_CAMBIAR", "1").strip() == "1"
FICHA_ESPERA = config.entero(CFG, "FICHA_ESPERA", 3)
FICHA_SEGUNDOS = config.entero(CFG, "FICHA_SEGUNDOS", 10)
APRENDIZAJE = CFG.get("MODO_APRENDIZAJE", "0").strip() == "1"
APAGADO_NOCTURNO = CFG.get("APAGADO_NOCTURNO", "").strip()
APRENDIZAJE_MAX_BYTES = 5 * 1024 * 1024
VOLVER = CFG.get("VOLVER_AL_CANAL", "1").strip() == "1"
AVISO_ANTES_DE_VOLVER = 30      # «Vuelvo a Antena 3 en 30 s»
ANTELACION_RECORDATORIO = config.entero(CFG, "RECORDATORIO_ANTELACION", 60)
PREAVISO_RECORDATORIO = 120     # aviso en pantalla antes de cambiar de canal por un recordatorio

tv = PanasonicTVManager(tv_ip=TV_IP)
avisos = avisos_tv.AvisosTV(tv, CFG)
parar = threading.Event()
bloqueo = threading.Lock()
proc_logcat = None
vuelta = vuelta_mod.Vuelta(duracion_defecto=config.entero(CFG, "DURACION_PUBLI", 300)) if VOLVER else None
senal = senal_guia.SenalGuia(tras_zapeo=config.entero(CFG, "GUIA_TRAS_ZAPEO", 20),
                             calma=config.entero(CFG, "GUIA_CALMA", 480))

datos = estado.leer()
datos.update({"tv_ip": TV_IP, "silenciada": False, "fin_silencio": 0, "inicio": time.time(),
              "mute_segundos": MUTE_DURATION, "vuelta": vuelta.resumen() if vuelta else None})
ultimo_fin = 0.0
ultimo_numero = ("", 0.0)       # último número de canal visto en el rótulo de la TV
esperando_canal = ("", 0.0)     # canal al que vamos nosotros (ese cambio no es un zapeo del usuario)
aviso_vuelta_hecho = 0.0        # hora de vuelta de la que ya se ha avisado
preavisados = set()             # recordatorios ya preavisados en pantalla
fichas_vistas = {}              # canal de la guía -> inicio del programa cuya ficha ya se ha enseñado
vol_canales = rutinas.VolumenCanales(estable=config.entero(CFG, "VOLUMEN_ESTABLE", rutinas.ESTABLE),
                                     tras_cambio=config.entero(CFG, "VOLUMEN_TRAS_CAMBIO", rutinas.TRAS_CAMBIO))
VOLUMEN_CADA = float(CFG.get("VOLUMEN_CADA", "4") or 4)
despertador = rutinas.Despertador()
salida = rutinas.Salida()
casa = casa_mod.Casa()
cine_luces = False              # luces bajadas por el modo cine
casa_previo = {}                # último estado visto de la llamada y del timbre
ultimo_seguir = 0.0
cerrojo_fichas = threading.Lock()
negros = rutinas.ContadorNegros()
pulsaciones = []                # horas de las pulsaciones del botón de la ficha
fallos_de_linea = set()         # fallos al procesar una línea (se apunta cada uno una sola vez)
volumen_tocado = threading.Event()  # se ha pulsado una tecla de volumen en el mando
ficha_en_pantalla = [0.0]       # hasta cuándo se ve la ficha pedida con el mando
ficha_pedida = [0.0]            # cuándo se pidió la última con el mando
ficha_mostrada = [0.0]          # cuándo salió en la tele
QUITAR_TRAS = 2.0               # una pulsación antes de esto, con la ficha recién salida, no la quita


REGISTRO = None                 # en el programa de Windows se escribe aquí y no en la consola del menú
REGISTRO_MAX_BYTES = 2 * 1024 * 1024


def log(msg):
    linea = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    if REGISTRO:
        try:
            if os.path.exists(REGISTRO) and os.path.getsize(REGISTRO) > REGISTRO_MAX_BYTES:
                os.replace(REGISTRO, REGISTRO + ".1")
            with open(REGISTRO, "a", encoding="utf-8") as f:
                f.write(linea + "\n")
            return
        except OSError:
            pass
    print(linea, flush=True)


def mensajero():
    return whatsapp_privado.cargar(BASE)


def avisar(titulo, mensaje="", **extra):
    """Aviso en la pantalla de la TV sin parar al que llama (con la TV apagada tarda unos segundos)."""
    threading.Thread(target=avisos.mostrar, args=(titulo, mensaje), kwargs=extra, daemon=True).start()


def guardar(**cambios):
    with bloqueo:
        hoy = time.strftime("%Y-%m-%d")
        if datos.get("hoy") != hoy:
            datos.update({"hoy": hoy, "cortes_hoy": 0, "segundos_hoy": 0})
        datos.update(cambios)
        datos["silenciada"] = tv.silenciada_por_nosotros
        datos["fin_silencio"] = tv.fin_silencio if tv.silenciada_por_nosotros else 0
        datos["pausado"] = estado.pausado()
        datos["latido"] = time.time()
        estado.escribir(dict(datos))


# ------------------------------------------------------------ silencio
def al_terminar_silencio(restaurado):
    global ultimo_fin
    ultimo_fin = time.time()
    inicio = datos.get("inicio_silencio_actual") or ultimo_fin
    with bloqueo:
        datos["segundos_hoy"] = int(datos.get("segundos_hoy", 0)) + int(ultimo_fin - inicio)
    log("Sonido restaurado." if restaurado else "Fin del silencio (el sonido ya estaba puesto).")
    guardar()


def silenciar(motivo, segundos=MUTE_DURATION, manual=False):
    if not manual:
        if estado.pausado():
            log(f"Publicidad detectada ({motivo}) pero el silenciador está en pausa.")
            return
        if tv.silenciada_por_nosotros:
            return
        if time.time() - ultimo_fin < COOLDOWN_SECONDS:
            return
    if tv.silenciar_temporal(segundos, al_terminar=al_terminar_silencio):
        canal = datos.get("canal", "?")
        log(f"Silenciando {segundos}s ({motivo}) en {canal}. Lectura de mute fiable: {tv.lectura_mute_fiable}")
        with bloqueo:
            datos["cortes_hoy"] = int(datos.get("cortes_hoy", 0)) + 1
            datos["inicio_silencio_actual"] = time.time()
            datos["ultimo_corte"] = {"hora": time.strftime("%H:%M"), "canal": canal, "motivo": motivo}
        guardar()
    else:
        log(f"No se silencia ({motivo}): la TV ya estaba silenciada.")


# ------------------------------------------------------------ logcat
def registrar_aprendizaje(linea):
    ruta = estado.ruta("aprendizaje.log")
    try:
        if os.path.exists(ruta) and os.path.getsize(ruta) > APRENDIZAJE_MAX_BYTES:
            os.replace(ruta, ruta + ".1")
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def hora(t):
    return time.strftime("%H:%M:%S", time.localtime(t))


def al_cambiar_canal(nombre):
    log(f"Canal: {nombre}")
    guardar(canal=nombre, canal_desde=time.time())
    a = ajustes.leer()
    objetivo = vol_canales.cambio_canal(nombre, rutinas.tope_noche(a))
    if objetivo is not None and a["volumen_por_canal"]:
        temporizador = threading.Timer(1.5, poner_volumen_del_canal, args=(nombre, objetivo))
        temporizador.daemon = True
        temporizador.start()
    if not (esperando_canal[0] == nombre and time.time() < esperando_canal[1]):  # los cambios del hub, no
        temporizador = threading.Timer(FICHA_ESPERA, ficha_al_cambiar, args=(nombre,))
        temporizador.daemon = True
        temporizador.start()
    if vuelta is None:
        return
    propio = esperando_canal[0] == nombre and time.time() < esperando_canal[1]
    if vuelta.cambio_canal(nombre, propio=propio) == "restaurar":
        log(f"Te has ido a {nombre} durante los anuncios de {vuelta.origen}: "
            f"vuelvo a las {hora(vuelta.hora_vuelta)}.")
        if tv.silenciada_por_nosotros:
            al_terminar_silencio(tv.restaurar())
        avisar_vuelta_al_zapear()
    guardar(vuelta=vuelta.resumen())


def ficha_al_cambiar(nombre):
    """Ficha de lo que echan, la primera vez que llegas a ese programa. Si ya te has ido (zapeo rápido), nada."""
    if datos.get("canal") != nombre or not estado.interruptor("ficha_al_cambiar", FICHA_AL_CAMBIAR):
        return
    try:
        epg = GuiaEPG(CFG).ahora(nombre)
    except Exception as e:  # noqa: BLE001 - una guía rota no tumba el servicio
        log(f"Aviso en la ficha al cambiar de canal: {e}")
        return
    actual = epg.get("actual")
    if not actual:
        return
    clave = epg.get("canal_epg") or nombre
    with cerrojo_fichas:
        if fichas_vistas.get(clave) == actual["inicio_ts"]:
            return
        fichas_vistas[clave] = actual["inicio_ts"]
    t = ficha_tv.tarjeta(actual, nombre, plataformas=MediaInfoService.sin_anuncios(actual["titulo_busqueda"]))
    avisos.mostrar(t["titulo"], t["mensaje"], duracion=FICHA_SEGUNDOS, detalle=t["detalle"], imagen=t["imagen"],
                   pie=t["pie"], solo_app=True)


def tecla_del_mando(linea):
    """El botón de la ficha (amarillo, verde o dos veces «i»): enseña la ficha; otra vez, la quita."""
    m = _RE_TECLA.search(linea)
    if not m or int(m.group(2), 16) != 0:
        return
    if int(m.group(1), 16) in TECLAS_VOLUMEN:
        volumen_tocado.set()  # el volumen se mira ahora, en vez de cada pocos segundos
        return
    eleccion = BOTONES_FICHA.get(ajustes.leer().get("boton_ficha"))
    if not eleccion or int(m.group(1), 16) != eleccion[0]:
        pulsaciones.clear()
        return
    ahora = time.time()
    pulsaciones.append(ahora)
    del pulsaciones[:-eleccion[1]]
    if len(pulsaciones) < eleccion[1] or ahora - pulsaciones[0] > 1.5:
        return
    pulsaciones.clear()
    if ahora < ficha_en_pantalla[0]:
        # Medido el 3/11/2026: sin ver nada al momento se vuelve a pulsar (0,9 s después) y eso la quitaba
        # antes de verla. Mientras se prepara, o recién salida, otra pulsación no hace nada.
        if ficha_mostrada[0] < ficha_pedida[0] or ahora - ficha_mostrada[0] < QUITAR_TRAS:
            return
        ficha_en_pantalla[0] = 0.0
        log("Ficha quitada con el mando.")
        threading.Thread(target=avisos.ocultar, daemon=True).start()
    else:
        ficha_pedida[0] = ahora
        ficha_en_pantalla[0] = ahora + 60   # mientras se prepara (leer la guía tarda unos segundos)
        threading.Thread(target=ficha_con_el_mando, daemon=True).start()


def ficha_con_el_mando():
    try:
        ficha_ahora()
    finally:
        ficha_mostrada[0] = time.time()
        ficha_en_pantalla[0] = ficha_mostrada[0] + FICHA_SEGUNDOS + 5


def ficha_de_la_guia():
    """Con la guía de la tele abierta: la ficha del programa MARCADO en ella. False si no es la guía."""
    if not pantalla_tv.es_la_guia(tv._foco_actual()):
        return False
    filas = pantalla_tv.leer(tv)
    if not filas and avisos.version_instalada() < avisos_tv.VERSION_APP:
        log("La app de avisos de la tele es de una versión anterior (sin el lector de la guía): la pongo al día.")
        if avisos.al_dia():
            filas = pantalla_tv.leer(tv)
    marcado = pantalla_tv.programa_de_la_guia(filas)
    if not marcado:
        log("Botón de la ficha en la guía, pero no he podido leer el programa marcado.")
        return False
    guia = GuiaEPG(CFG)
    clave = guia.buscar_canal(marcado["canal"]) if marcado["canal"] else None
    programa = None
    if clave and marcado["inicio_ts"] and marcado["fin_ts"]:
        programa = guia.a_la_hora(clave, (marcado["inicio_ts"] + marcado["fin_ts"]) / 2)
    if not programa:
        programa = pantalla_tv.como_programa(marcado)
    elif programa.get("inicio_ts"):
        programa = dict(programa, inicio=pantalla_tv._hora(programa["inicio_ts"], time.time()))
    if not programa.get("descripcion"):
        programa["descripcion"] = marcado["detalle"]
    log(f"Ficha pedida con el mando en la guía: «{programa['titulo']}» en {marcado['canal'] or '?'}.")
    busqueda = programa.get("titulo_busqueda") or pantalla_tv.titulo_para_buscar(programa["titulo"])[0]
    ficha = MediaInfoService.buscar_info_pelicula(busqueda, epg=programa)
    t = ficha_tv.tarjeta(programa, marcado["canal"], ficha=ficha, plataformas=MediaInfoService.sin_anuncios(busqueda))
    avisos.mostrar(t["titulo"], t["mensaje"], duracion=FICHA_SEGUNDOS + 5, detalle=t["detalle"], imagen=t["imagen"],
                   pie=t["pie"], solo_app=True)
    return True


def ficha_ahora():
    """La ficha pedida con el mando: la del programa marcado si está la guía abierta; si no, la de lo que echan."""
    if ficha_de_la_guia():
        return
    nombre = datos.get("canal") or ""
    actual = GuiaEPG(CFG).ahora(nombre).get("actual") if nombre else None
    if not actual:
        avisar("Sin ficha", f"La guía no trae lo que echan en {nombre}." if nombre else "No sé qué canal estás viendo.")
        return
    log(f"Ficha pedida con el mando: «{actual['titulo']}» en {nombre}.")
    ficha = MediaInfoService.buscar_info_pelicula(actual["titulo_busqueda"], epg=actual)
    t = ficha_tv.tarjeta(actual, nombre, ficha=ficha,
                         plataformas=MediaInfoService.sin_anuncios(actual["titulo_busqueda"]))
    avisos.mostrar(t["titulo"], t["mensaje"], duracion=FICHA_SEGUNDOS + 5, detalle=t["detalle"], imagen=t["imagen"],
                   pie=t["pie"], solo_app=True)


def lo_que_se_ve():
    """Para el DNS: el canal de la TDT o, si se está en otra app, su nombre."""
    app = datos.get("app") or ""
    if not app or app == PAQUETE_TDT:
        return datos.get("canal") or ""
    nombres = {v.split("/")[0]: k for k, v in tv.get_known_apps().items()}
    return nombres.get(app, app)


def avisar_vuelta_al_zapear():
    global aviso_vuelta_hecho
    quedan = int(round(vuelta.hora_vuelta - time.time()))
    if quedan <= AVISO_ANTES_DE_VOLVER + 5:
        # Tan cerca que el aviso de los 30 s saldría justo detrás: se da uno solo
        aviso_vuelta_hecho = vuelta.hora_vuelta
        avisar(f"Vuelvo a {vuelta.origen} en {max(quedan, 1)} s", "Si no quieres, pulsa «No volver» en el móvil.")
    else:
        avisar(f"Anuncios en {vuelta.origen}", f"Vuelvo a {vuelta.origen} a las {hora(vuelta.hora_vuelta)[:5]}.")


def avisar_antes_de_volver():
    """«Vuelvo a Antena 3 en 30 s», una vez por cada vuelta."""
    global aviso_vuelta_hecho
    if vuelta.estado != vuelta_mod.FUERA or not vuelta.hora_vuelta or aviso_vuelta_hecho == vuelta.hora_vuelta:
        return
    quedan = vuelta.hora_vuelta - time.time()
    if 5 < quedan <= AVISO_ANTES_DE_VOLVER:
        aviso_vuelta_hecho = vuelta.hora_vuelta
        avisar(f"Vuelvo a {vuelta.origen} en {int(round(quedan))} s", "Si no quieres, pulsa «No volver» en el móvil.")


def poner_volumen_del_canal(nombre, objetivo):
    """El volumen al que dejaste este canal la última vez."""
    if datos.get("canal") != nombre:
        return
    actual = tv.volumen_leer()
    if actual is None or actual == objetivo:
        vol_canales.pendiente = None
        return
    if not tv.volumen_poner(objetivo):
        vol_canales.pendiente = None
    else:
        vol_canales.puesto_por_el_hub(objetivo)
        log(f"Volumen de {nombre}: {actual} -> {objetivo} (el que tenía la última vez).")


def revisar_volumen():
    """Cada pocos segundos: tope del modo noche y aprender el volumen de cada canal."""
    a = ajustes.leer()
    if not (a["volumen_por_canal"] or a["noche_activo"]):
        return
    if datos.get("conexion") not in (None, "device"):  # con la tele apagada no se le pregunta nada
        return
    v = tv.volumen_leer()
    if v is None:
        return
    if datos.get("canal") and vol_canales.canal != datos.get("canal"):
        vol_canales.cambio_canal(datos.get("canal"))
        vol_canales.pendiente = None  # al arrancar el servicio: no hay volumen pendiente de poner
    tope = rutinas.tope_noche(a)
    if tope is not None and v > tope:
        if tv.volumen_poner(tope):
            vol_canales.puesto_por_el_hub(tope)
            log(f"Modo noche: volumen de {v} a {tope}.")
        return
    if a["volumen_por_canal"] and not (tope is not None and v >= tope):  # el tope de la noche no es tu volumen
        aprendido = vol_canales.observar(v, silenciada=tv.silenciada_por_nosotros)
        if aprendido is not None:
            log(f"Volumen de {vol_canales.canal}: {aprendido} (lo pondré al volver a este canal).")


def bucle_volumen():
    """Se mira el volumen cuando se toca en el mando (y, por si acaso, cada VOLUMEN_CADA s), no sin parar."""
    while not parar.is_set():
        if volumen_tocado.wait(VOLUMEN_CADA):
            volumen_tocado.clear()
            if parar.wait(2.5):  # que se acabe de pulsar
                break
            volumen_tocado.clear()
        try:
            revisar_volumen()
        except Exception as e:  # noqa: BLE001
            log(f"Aviso en el volumen: {e}")


# ------------------------------------------------------- despertador, salir de casa, seguir y la casa
def revisar_despertador():
    a = ajustes.leer()
    if not despertador.toca(a):
        return
    log(f"Despertador: enciendo la tele en el canal {a['despertador_canal']}.")
    mac = a["tv_mac"] or tv.tv_mac or presencia.mac_de(TV_IP)
    if mac:
        tv.tv_mac = mac
    tv.encender()
    for _ in range(20):
        if tv.esta_encendida() is True:
            break
        if parar.wait(2):
            return
    else:
        log("Despertador: la tele no se ha encendido (¿tiene activado el encendido por red?).")
        return
    parar.wait(5)
    tv.poner_canal(a["despertador_canal"], esperar=parar.wait)
    parar.wait(3)
    tv.volumen_poner(a["despertador_volumen"])
    avisar("Buenos días", time.strftime("%H:%M"))


def revisar_salida():
    a = ajustes.leer()
    if not (a["salir_activo"] and a["salir_ip"]):
        salida.observar(a, True, None, None)
        return
    presente = presencia.responde(a["salir_ip"])
    encendida = None if presente else tv.esta_encendida()
    huella = None if presente else (tv.volumen_leer(), datos.get("canal"))
    accion = salida.observar(a, presente, encendida, huella)
    if accion == "avisar":
        log(f"No veo el móvil ({a['salir_ip']}) desde hace {a['salir_minutos']} min: aviso antes de apagar.")
        avisar("¿Hay alguien en casa?", "No veo tu móvil: apago la tele en 1 minuto. Si estás, cambia el volumen o de canal.",
               duracion=20)
    elif accion == "apagar":
        log("Nadie en casa: apago la tele.")
        tv.apagar()


def programar_seguidos():
    global ultimo_seguir
    if time.time() - ultimo_seguir < 300:
        return
    ultimo_seguir = time.time()
    guia = GuiaEPG(CFG)._datos()
    if not guia:
        return
    for r in seguir.programar(guia["canales"]):
        log(f"Sigues «{r['titulo']}»: recordatorio a las {hora(r['inicio'])[:5]} en {r['canal']}.")


def revisar_cine():
    global cine_luces
    a = ajustes.leer()
    if not (a["ha_cine"] and casa.configurada()):
        return
    canal = datos.get("canal") or ""
    actual = GuiaEPG(CFG).ahora(canal).get("actual") if canal else None
    pelicula = casa_mod.es_cine(actual) and tv.esta_encendida() is True
    if pelicula and not cine_luces and not tv.silenciada_por_nosotros:
        if casa.luces_cine():
            cine_luces = True
            log(f"Modo cine: luces bajadas para «{actual['titulo']}».")
    elif not pelicula and cine_luces:
        casa.luces_como_antes()
        cine_luces = False
        log("Modo cine: luces como estaban.")


def luces_en_los_anuncios():
    """En los anuncios, las luces como estaban; el modo cine las vuelve a bajar al acabar."""
    global cine_luces
    if cine_luces:
        cine_luces = False
        threading.Thread(target=casa.luces_como_antes, daemon=True).start()


def revisar_llamada_y_timbre():
    a = ajustes.leer()
    if not casa.configurada():
        return
    if a["ha_sensor_llamada"]:
        st = casa.estado(a["ha_sensor_llamada"])
        antes = casa_previo.get("llamada")
        casa_previo["llamada"] = st
        if st == "ringing" and antes != "ringing":
            log("Llamada en el móvil: silencio la tele.")
            if tv.silenciar_temporal(180, al_terminar=al_terminar_silencio):
                casa_previo["silencio_llamada"] = True
            avisar("Te llaman al móvil", "He silenciado la tele.", duracion=10)
        elif st == "idle" and antes in ("ringing", "offhook") and casa_previo.pop("silencio_llamada", False):
            log("Fin de la llamada: devuelvo el sonido.")
            al_terminar_silencio(tv.restaurar())
    if a["ha_timbre"]:
        st = casa.estado(a["ha_timbre"])
        antes = casa_previo.get("timbre")
        casa_previo["timbre"] = st
        evento = a["ha_timbre"].startswith("event.")
        if st and antes is not None and ((evento and st != antes) or (not evento and st == "on" and antes != "on")):
            foto = casa.foto()
            imagen = ""
            if foto:
                with open(estado.ruta("camara.jpg"), "wb") as f:
                    f.write(foto)
                imagen = f"http://{IP_HUB}:{config.entero(CFG, 'WEB_PORT', 8080)}/camara.jpg?t={int(time.time())}"
            log("Llaman a la puerta.")
            avisar("Llaman a la puerta", "", duracion=20, imagen=imagen)


def bucle_rutinas():
    cuenta = 0
    while not parar.wait(3):
        cuenta += 1
        for cada, funcion in ((1, revisar_llamada_y_timbre), (7, revisar_despertador), (10, revisar_cine),
                              (20, revisar_salida), (20, programar_seguidos)):
            if cuenta % cada:
                continue
            try:
                funcion()
            except Exception as e:  # noqa: BLE001 - una rutina rota no tumba el servicio
                log(f"Aviso en {funcion.__name__}: {e}")


def _ip_hub():
    import socket  # noqa: PLC0415

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


IP_HUB = _ip_hub()


def al_empezar_publi(motivo, manual=False):
    segundos = MUTE_DURATION
    canal = datos.get("canal")
    if vuelta is not None and vuelta.datos["duraciones"].get(canal):
        segundos = vuelta.duracion_estimada(canal)  # lo que suelen durar de verdad los cortes de ese canal
    silenciar(motivo, segundos=segundos, manual=manual)
    luces_en_los_anuncios()
    if vuelta is not None and (manual or not estado.pausado()):
        vuelta.publi_empieza(datos.get("canal"))
        guardar(vuelta=vuelta.resumen())


def al_acabar_publi(motivo):
    if vuelta is not None:
        segundos = vuelta.publi_termina(datos.get("canal"))
        if segundos:
            log(f"Fin de los anuncios en {datos.get('canal')} ({motivo}): han durado {segundos} s.")
        guardar(vuelta=vuelta.resumen())
    if tv.silenciada_por_nosotros:
        al_terminar_silencio(tv.restaurar())


def volver_al_origen():
    """Sintoniza el canal donde empezaron los anuncios."""
    global esperando_canal
    origen = vuelta.origen
    numero = vuelta.numero(origen)
    esperando_canal = (origen, time.time() + 15)
    if numero:
        log(f"Volviendo a {origen} (canal {numero}).")
        tv.ir_a_numero(numero)
    elif vuelta.saltos == 1:
        log(f"Volviendo a {origen} con «canal anterior» (no sé su número).")
        tv.canal_anterior()
    else:
        log(f"No puedo volver a {origen}: no sé su número y has cambiado de canal varias veces.")
        vuelta.cancelar()
    guardar(vuelta=vuelta.resumen())


def procesar_linea(linea):
    global ultimo_numero
    linea = linea.strip()
    if not linea:
        return
    if "avg_pixel_luma" in linea:  # 8 por segundo: se despachan sin mirar nada más
        m = _RE_LUMA.search(linea)
        cerrado = negros.muestra(int(m.group(1)), datos.get("canal") or "") if m else None
        if cerrado:
            apuntar_negros(cerrado)
        return
    rotulo = tv.extraer_rotulo(linea)
    if rotulo and vuelta is not None:
        if rotulo[0] == "numero":
            ultimo_numero = (rotulo[1], time.time())
        elif time.time() - ultimo_numero[1] < 3:
            vuelta.anotar_numero(rotulo[1], ultimo_numero[0])
    canal = tv.extraer_canal(linea)
    if canal and canal["channel_id"] != senal.canal_id:
        senal.cambio_canal(canal["channel_id"])
    if canal and canal["name"] != datos.get("canal"):
        al_cambiar_canal(canal["name"])
    tipo = senal.procesar(linea)
    if tipo:
        al_ver_senal_guia(tipo)
    if "u8KeyCode" in linea:
        tecla_del_mando(linea)
    if APRENDIZAJE:
        registrar_aprendizaje(linea)
    for patron in PATRONES:
        if patron in linea:
            al_empezar_publi(f"marcador {patron}")
            break
    for patron in PATRONES_FIN:
        if patron in linea:
            al_acabar_publi(f"marcador {patron}")
            break


def al_ver_senal_guia(tipo):
    """Novedad en la guía del canal que se ve, fuera de un zapeo. Se apunta siempre; silencia solo si se ha activado."""
    canal = datos.get("canal")
    senal_guia.apuntar(tipo, canal)
    if tipo != "inicio":
        return
    if estado.senal_guia_silencia(GUIA_SILENCIA):
        log(f"Señal de la guía en {canal}: posibles anuncios.")
        al_empezar_publi("señal de la guía")
    else:
        log(f"Señal de la guía en {canal} (solo se apunta).")


def apuntar_negros(fila):
    ruta = estado.ruta("negros.jsonl")
    try:
        if os.path.exists(ruta) and os.path.getsize(ruta) > 1024 * 1024:
            os.replace(ruta, ruta + ".1")
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except OSError:
        pass


def orden_logcat():
    escucha = ["logcat"] + BUFFERS_LOGCAT + ["-v", "time", "-T", "1"] + ETIQUETAS + ["*:S"]
    if not FILTRAR_EN_TV or APRENDIZAJE:  # aprendiendo hay que verlo todo
        return tv.adb_base + ["-s", TV_IP] + escucha
    claves = list(LINEAS_UTILES) + PATRONES + PATRONES_FIN
    filtro = "grep --line-buffered -F " + " ".join("-e " + shlex.quote(c) for c in claves)
    return tv.adb_base + ["-s", TV_IP, "shell", " ".join(shlex.quote(a) for a in escucha) + " | " + filtro]


def bucle_logcat():
    global proc_logcat
    espera = 5
    while not parar.is_set():
        inicio = time.time()
        try:
            if not tv.connect():
                log(f"La TV ({TV_IP}) no responde. Reintento en {espera}s.")
            else:
                orden = orden_logcat()
                proc_logcat = subprocess.Popen(orden, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                               stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                               errors="replace", bufsize=1, creationflags=SIN_VENTANA)
                log("Escuchando la señal de la TV...")
                for linea in proc_logcat.stdout:
                    if parar.is_set():
                        break
                    try:
                        procesar_linea(linea)
                    except Exception as e:  # noqa: BLE001 - una línea rara no corta la escucha
                        fallo = f"{type(e).__name__}: {e}"
                        if fallo not in fallos_de_linea:
                            fallos_de_linea.add(fallo)
                            log(f"Aviso: no he podido procesar una línea de la TV ({fallo}).")
        except Exception as e:  # noqa: BLE001 - el servicio no se cae nunca por un fallo de ADB
            log(f"Aviso en el bucle de escucha: {e}")
        finally:
            # Siempre se cierra el adb logcat de esta vuelta: si no, cada fallo deja uno vivo para siempre
            if proc_logcat is not None:
                try:
                    proc_logcat.terminate()
                except OSError:
                    pass
                proc_logcat = None
        if parar.is_set():
            break
        # Si la escucha dura poco (TV apagada), se espacian los reintentos hasta 60 s
        espera = 5 if time.time() - inicio > 60 else min(espera * 2, 60)
        parar.wait(espera)


# ------------------------------------------------------- hilos auxiliares
def bucle_latido():
    while not parar.wait(10):
        guardar(conexion=tv.estado_conexion())
        if DNS_ACTIVO:  # qué app está delante, para apuntar con cada bloqueo dónde ha sido
            m = re.search(r"u0 ([\w.]+)/", tv._foco_actual() or "")
            datos["app"] = m.group(1) if m else ""


def arrancar_dns():
    if not DNS_ACTIVO:
        return
    servidor = dns_hub.ServidorDNS(puerto=config.entero(CFG, "DNS_PUERTO", 53),
                                   superior=CFG.get("DNS_SUPERIOR") or "1.1.1.1", donde=lo_que_se_ve)
    if servidor.arrancar():
        log(f"DNS antirrastreo en el puerto {servidor.puerto} ({len(servidor.dominios)} dominios en la lista).")
        guardar(dns={"activo": True, "puerto": servidor.puerto, "error": ""})
    else:
        log(f"DNS antirrastreo: no se ha podido abrir el puerto {servidor.puerto} ({servidor.error}).")
        guardar(dns={"activo": False, "puerto": servidor.puerto, "error": servidor.error})


def bucle_ordenes():
    while not parar.wait(0.5):
        if estado.tomar_orden("silenciar"):
            senal_guia.apuntar("boton", datos.get("canal"))
            al_empezar_publi("botón del mando web", manual=True)
        if estado.tomar_orden("restaurar"):
            senal_guia.apuntar("fin", datos.get("canal"))
            log("Restaurar sonido pedido desde el mando web.")
            al_acabar_publi("botón «devolver el sonido»")
        if vuelta is None:
            continue
        if estado.tomar_orden("volver_ya") and vuelta.volver_ya():
            log("Volver ya, pedido desde el mando web.")
        if estado.tomar_orden("no_volver") and vuelta.cancelar():
            log("Vuelta al canal cancelada desde el mando web.")
            guardar(vuelta=vuelta.resumen())
        antes = vuelta.estado
        if vuelta.tick() == "volver":
            volver_al_origen()
        elif vuelta.estado != antes:
            guardar(vuelta=vuelta.resumen())
        avisar_antes_de_volver()


# ------------------------------------------------------- recordatorios
def bucle_recordatorios():
    while not parar.wait(5):
        try:
            revisar_recordatorios()
        except Exception as e:  # noqa: BLE001 - un recordatorio roto no tumba el servicio
            log(f"Aviso en los recordatorios: {e}")


def revisar_recordatorios(ahora=None):
    ahora = ahora or time.time()
    for rec in recordatorios.pendientes():
        momento = float(rec.get("inicio") or 0) - ANTELACION_RECORDATORIO
        if ahora >= momento:
            disparar_recordatorio(rec, ahora)
        elif (rec.get("accion") in ("tele", "ambos") and rec["id"] not in preavisados
              and momento - PREAVISO_RECORDATORIO <= ahora):
            preavisados.add(rec["id"])
            minutos = max(1, int(round((momento - ahora) / 60)))
            avisar(f"En {minutos} min: «{rec.get('titulo', '')}»",
                   f"Pondré {rec.get('nombre', '')} en la tele. Si no quieres, bórralo en el móvil.")
    recordatorios.limpiar(ahora)


def disparar_recordatorio(rec, ahora):
    if not recordatorios.tomar(rec):
        return
    if ahora - float(rec.get("inicio") or 0) > recordatorios.CADUCIDAD:
        resultado = "no se hizo: el hub no estaba en marcha a esa hora"
    else:
        partes = []
        if rec.get("accion") in ("tele", "ambos"):
            partes.append(poner_canal_del_recordatorio(rec))
        if rec.get("accion") in ("whatsapp", "ambos"):
            partes.append(whatsapp_del_recordatorio(rec, puesta=bool(partes) and partes[0].startswith("tele puesta")))
        resultado = "; ".join(partes)
    recordatorios.apuntar(rec, resultado)
    log(f"Recordatorio «{rec.get('titulo')}» en {rec.get('nombre')}: {resultado}.")


def poner_canal_del_recordatorio(rec):
    numero = str(rec.get("numero") or "")
    if not numero.isdigit():
        return "sin número de canal"
    if tv.esta_encendida() is not True:
        return "la tele estaba apagada"
    if vuelta is not None and vuelta.estado != vuelta_mod.INACTIVA:
        vuelta.cancelar()  # el recordatorio manda sobre la vuelta de los anuncios
        guardar(vuelta=vuelta.resumen())
    if tv.silenciada_por_nosotros:
        al_terminar_silencio(tv.restaurar())
    tv.poner_canal(numero, esperar=parar.wait)
    avisar(f"Empieza «{rec.get('titulo', '')}»", f"{rec.get('nombre', '')} · {hora(float(rec['inicio']))[:5]}")
    return f"tele puesta en el canal {numero}"


def whatsapp_del_recordatorio(rec, puesta=False):
    m = mensajero()
    if not m:
        return "WhatsApp sin configurar"
    modulo, creds = m
    texto = (f"⏰ *Recordatorio TV*\nEmpieza *{rec.get('titulo', '')}* en *{rec.get('nombre', '')}* "
             f"a las {hora(float(rec['inicio']))[:5]}.")
    if puesta:
        texto += "\nHe puesto la tele en ese canal."
    res = modulo.MensajeroWhatsApp(api_key=creds["API_KEY"]).enviar_texto(creds["TELEFONO_DESTINO"], texto)
    return "WhatsApp enviado" if res.get("ok") else f"WhatsApp no enviado ({res.get('error')})"


def bucle_apagado_nocturno():
    if not APAGADO_NOCTURNO:
        return
    log(f"Apagado nocturno programado a las {APAGADO_NOCTURNO}.")
    hecho = ""
    while not parar.wait(30):
        hoy = time.strftime("%Y-%m-%d")
        if time.strftime("%H:%M") != APAGADO_NOCTURNO or hecho == hoy:
            continue
        hecho = hoy
        if tv.esta_encendida() is not True:
            continue
        log("Apagado nocturno: bajando volumen y apagando la TV.")
        if not avisos.mostrar("Apagado nocturno", "La TV se apagará en 1 minuto.", duracion=15):
            tv.post_tv_notification("Apagado nocturno", "La TV se apagará en 1 minuto.")
        for _ in range(4):
            if parar.wait(15):
                return
            tv.volume_down()
        tv.apagar()
        guardar(ultimo_apagado_nocturno=time.strftime("%Y-%m-%d %H:%M"))


# ------------------------------------------------------------ arranque
def cerrar():
    """Para todo y devuelve el sonido si lo habíamos quitado nosotros. Se puede llamar más de una vez."""
    if parar.is_set():
        return
    parar.set()
    log("Parando el servicio...")
    with tv._lock:  # si se está silenciando justo ahora, se espera a que acabe para poder devolverlo
        if tv.silenciada_por_nosotros:
            log("Restaurando el sonido antes de salir.")
            tv.restaurar()
    if proc_logcat is not None:
        try:
            proc_logcat.terminate()
        except OSError:
            pass
    with bloqueo:
        datos["latido"] = 0
    estado.escribir(dict(datos))


def apagar_limpio(*_):
    if parar.is_set():
        return
    cerrar()
    raise SystemExit(0)


def arrancar_hilos():
    guardar(conexion=tv.estado_conexion(), dns=None)
    arrancar_dns()
    for objetivo in (bucle_latido, bucle_ordenes, bucle_apagado_nocturno, bucle_recordatorios, bucle_volumen,
                     bucle_rutinas):
        threading.Thread(target=objetivo, daemon=True).start()


def en_segundo_plano(registro=None):
    """Para el programa de Windows: todo en hilos (las señales solo se atienden en el hilo principal)
    y, si se indica, el registro a un fichero para no mezclarlo con el menú de la consola."""
    global REGISTRO
    REGISTRO = registro
    presentacion()
    arrancar_hilos()
    threading.Thread(target=bucle_logcat, daemon=True).start()


def main():
    signal.signal(signal.SIGINT, apagar_limpio)
    signal.signal(signal.SIGTERM, apagar_limpio)
    presentacion()
    arrancar_hilos()
    try:
        bucle_logcat()
    finally:
        if not parar.is_set():
            try:
                apagar_limpio()
            except SystemExit:
                pass


def presentacion():
    log("=======================================================")
    log(" Panasonic TV Hub - silenciador automático de publicidad")
    log(f" TV: {TV_IP} | silencio: {MUTE_DURATION}s | patrones: {', '.join(PATRONES) or 'ninguno (solo el botón)'}")
    if DESCARTADOS:
        log(f" Se ignoran {', '.join(DESCARTADOS)}: la TV los escribe cada 30 s, haya anuncios o no.")
    if vuelta is not None:
        log(" Vuelta al canal activa: si cambias de canal en los anuncios, la TV vuelve sola.")
    log(f" Avisos en la TV: {'en el ' + avisos.posicion + ', letra ' + str(avisos.tamano) if avisos.activo else 'desactivados'}"
        f" | recordatorios: {ANTELACION_RECORDATORIO} s antes de empezar")
    if APRENDIZAJE:
        log(f" MODO APRENDIZAJE: guardando el logcat en {estado.ruta('aprendizaje.log')}")
    log("=======================================================")


if __name__ == "__main__":
    main()
