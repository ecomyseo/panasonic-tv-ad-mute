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

import os
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
import senal_guia  # noqa: E402
import vuelta as vuelta_mod  # noqa: E402
import whatsapp_privado  # noqa: E402
from tv_manager import SIN_VENTANA, PanasonicTVManager  # noqa: E402

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
GUIA_SILENCIA = CFG.get("GUIA_SILENCIA", "0").strip() == "1"
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


def avisar(titulo, mensaje=""):
    """Aviso en la pantalla de la TV sin parar al que llama (con la TV apagada tarda unos segundos)."""
    threading.Thread(target=avisos.mostrar, args=(titulo, mensaje), daemon=True).start()


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


def al_empezar_publi(motivo, manual=False):
    segundos = MUTE_DURATION
    canal = datos.get("canal")
    if vuelta is not None and vuelta.datos["duraciones"].get(canal):
        segundos = vuelta.duracion_estimada(canal)  # lo que suelen durar de verdad los cortes de ese canal
    silenciar(motivo, segundos=segundos, manual=manual)
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


def bucle_logcat():
    global proc_logcat
    espera = 5
    while not parar.is_set():
        inicio = time.time()
        try:
            if not tv.connect():
                log(f"La TV ({TV_IP}) no responde. Reintento en {espera}s.")
            else:
                orden = tv.adb_base + ["-s", TV_IP, "logcat", "-v", "time", "-T", "1"] + ETIQUETAS + ["*:S"]
                proc_logcat = subprocess.Popen(orden, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                               stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                               errors="replace", bufsize=1, creationflags=SIN_VENTANA)
                log("Escuchando la señal de la TV...")
                for linea in proc_logcat.stdout:
                    if parar.is_set():
                        break
                    procesar_linea(linea)
                proc_logcat.terminate()
                proc_logcat = None
        except Exception as e:  # noqa: BLE001 - el servicio no se cae nunca por un fallo de ADB
            log(f"Aviso en el bucle de escucha: {e}")
        if parar.is_set():
            break
        # Si la escucha dura poco (TV apagada), se espacian los reintentos hasta 60 s
        espera = 5 if time.time() - inicio > 60 else min(espera * 2, 60)
        parar.wait(espera)


# ------------------------------------------------------- hilos auxiliares
def bucle_latido():
    while not parar.wait(10):
        guardar(conexion=tv.estado_conexion())


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
    guardar(conexion=tv.estado_conexion())
    for objetivo in (bucle_latido, bucle_ordenes, bucle_apagado_nocturno, bucle_recordatorios):
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
