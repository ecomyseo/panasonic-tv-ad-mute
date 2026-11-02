"""
DNS antirrastreo del propio hub, con estadísticas de qué se ha bloqueado y en qué canal.

Pensado para la Raspberry (siempre encendida). APAGADO de fábrica (`DNS_ACTIVO=0`). Para usarlo:
  1. DNS_ACTIVO=1 en la configuración (el servicio escucha en el puerto 53 de la red de casa).
  2. En la tele, Ajustes → Red → Ethernet/Wi-Fi → Configuración IP → Estática: DNS 1 = la IP del hub, DNS 2 = la
     del router (si el hub se apaga, la tele sigue teniendo Internet).
  3. Quitar el «DNS antirrastreo» de AdGuard del mando: con un DNS privado la tele se salta el del hub.

Lo que está en la lista se contesta con 0.0.0.0 (o ::) y se apunta con la hora y lo que se estaba viendo; lo demás
se pregunta al DNS de verdad (DNS_SUPERIOR) y se devuelve tal cual. Solo atiende a la red de casa.
"""

import ipaddress
import json
import os
import socket
import socketserver
import struct
import threading
import time

import estado

FICHERO = "dns_bloqueos.jsonl"
EXTRA = "dns_bloquear.txt"        # en la carpeta de estado: un dominio por línea, para añadir los tuyos
MAX_BYTES = 2 * 1024 * 1024

# Rastreo de audiencias y publicidad dirigida de la TDT (HbbTV) y telemetría de la tele
LISTA = (
    "smartclip.net", "smartclip.com", "sunmedia.tv", "flashtalking.com", "scorecardresearch.com",
    "imasdk.googleapis.com", "doubleclick.net", "googlesyndication.com", "google-analytics.com",
    "app-measurement.com", "firebase-logging.admob.com", "telemetry.panasonic.com", "connect.panasonic.biz",
    "device-metrics-us.amazon.com", "adsrvr.org", "adnxs.com", "spotxchange.com", "springserve.com",
    "tvping.com", "kantarmedia.com", "comscore.com", "chartbeat.net", "xiti.com", "omtrdc.net",
)


def _privada(ip: str) -> bool:
    try:
        d = ipaddress.ip_address(ip)
        return d.is_private or d.is_loopback or d.is_link_local
    except ValueError:
        return False


def leer_pregunta(paquete: bytes):
    """(nombre, tipo, fin de la pregunta) de una consulta DNS, o None si no se entiende."""
    if len(paquete) < 17 or struct.unpack(">H", paquete[4:6])[0] != 1:
        return None
    partes, i = [], 12
    while i < len(paquete):
        largo = paquete[i]
        if largo == 0:
            i += 1
            break
        if largo & 0xC0 or i + 1 + largo > len(paquete):
            return None
        partes.append(paquete[i + 1:i + 1 + largo].decode("ascii", "replace").lower())
        i += 1 + largo
    else:
        return None
    if i + 4 > len(paquete):
        return None
    tipo = struct.unpack(">H", paquete[i:i + 2])[0]
    return ".".join(partes), tipo, i + 4


def respuesta_bloqueo(paquete: bytes, tipo: int, fin: int) -> bytes:
    """0.0.0.0 para A, :: para AAAA y una respuesta vacía para lo demás (como hace Pi-hole)."""
    ident = paquete[:2]
    banderas = 0x8180 | (struct.unpack(">H", paquete[2:4])[0] & 0x0100)
    respuestas = 1 if tipo in (1, 28) else 0
    cabecera = ident + struct.pack(">HHHHH", banderas, 1, respuestas, 0, 0)
    pregunta = paquete[12:fin]
    if not respuestas:
        return cabecera + pregunta
    datos = b"\x00" * (4 if tipo == 1 else 16)
    return cabecera + pregunta + struct.pack(">HHHIH", 0xC00C, tipo, 1, 60, len(datos)) + datos


def lista_de_bloqueo() -> set:
    dominios = set(LISTA)
    try:
        with open(estado.ruta(EXTRA), encoding="utf-8") as f:
            dominios.update(l.strip().lower().lstrip("*.") for l in f if l.strip() and not l.startswith("#"))
    except OSError:
        pass
    return dominios


def bloqueado(nombre: str, dominios) -> str:
    """El dominio de la lista que lo bloquea ('' si no está): vale el propio nombre o cualquiera de sus padres."""
    partes = nombre.lower().rstrip(".").split(".")
    for i in range(len(partes) - 1):
        candidato = ".".join(partes[i:])
        if candidato in dominios:
            return candidato
    return ""


def apuntar(dominio, canal, cliente, momento=None):
    ruta = estado.ruta(FICHERO)
    try:
        if os.path.exists(ruta) and os.path.getsize(ruta) > MAX_BYTES:
            os.replace(ruta, ruta + ".1")
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": round(momento or time.time(), 1), "dominio": dominio, "canal": canal or "",
                                "cliente": cliente}, ensure_ascii=False) + "\n")
    except OSError:
        pass


class ServidorDNS:
    def __init__(self, puerto=53, superior="1.1.1.1", donde=lambda: "", escuchar="0.0.0.0"):
        self.puerto = puerto
        self.superior = superior
        self.donde = donde            # qué se está viendo (canal o app), para apuntarlo con cada bloqueo
        self.escuchar = escuchar
        self.dominios = lista_de_bloqueo()
        self.servidor = None
        self.error = ""

    def contestar(self, paquete: bytes, cliente: str):
        if not _privada(cliente):
            return None  # nada de servir a Internet (un DNS abierto se usa para ataques)
        pregunta = leer_pregunta(paquete)
        if not pregunta:
            return None  # lo que no es una consulta DNS no se reenvía
        if pregunta:
            nombre, tipo, fin = pregunta
            regla = bloqueado(nombre, self.dominios)
            if regla:
                apuntar(nombre, self.donde(), cliente)
                return respuesta_bloqueo(paquete, tipo, fin)
        host, _, puerto = self.superior.partition(":")
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(3)
        try:
            s.sendto(paquete, (host, int(puerto or 53)))
            return s.recvfrom(4096)[0]
        except OSError:
            return None
        finally:
            s.close()

    def arrancar(self) -> bool:
        dueno = self

        class Manejador(socketserver.BaseRequestHandler):
            def handle(self):
                datos, sock = self.request
                respuesta = dueno.contestar(datos, self.client_address[0])
                if respuesta:
                    sock.sendto(respuesta, self.client_address)

        class Servidor(socketserver.ThreadingMixIn, socketserver.UDPServer):
            daemon_threads = True

        try:
            self.servidor = Servidor((self.escuchar, self.puerto), Manejador)
        except OSError as e:
            self.error = str(e)
            return False
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()
        return True

    def parar(self):
        if self.servidor:
            self.servidor.shutdown()
            self.servidor.server_close()
            self.servidor = None


def _leer(desde):
    filas = []
    for nombre in (FICHERO + ".1", FICHERO):
        try:
            with open(estado.ruta(nombre), encoding="utf-8") as f:
                for linea in f:
                    try:
                        fila = json.loads(linea)
                    except ValueError:
                        continue
                    if isinstance(fila, dict) and float(fila.get("t") or 0) >= desde:
                        filas.append(fila)
        except OSError:
            continue
    return filas


def estadisticas(dias=7, ahora=None) -> dict:
    """Bloqueos de los últimos días: total, hoy, por canal (con sus dominios), por dominio y los últimos."""
    ahora = ahora or time.time()
    filas = _leer(ahora - dias * 86400)
    inicio_hoy = time.mktime(time.localtime(ahora)[:3] + (0, 0, 0, 0, 0, -1))

    def base(dominio):
        partes = dominio.split(".")
        return ".".join(partes[-2:]) if len(partes) >= 2 else dominio

    canales, dominios = {}, {}
    for f in filas:
        d = base(f["dominio"])
        dominios[d] = dominios.get(d, 0) + 1
        c = canales.setdefault(f["canal"] or "?", {})
        c[d] = c.get(d, 0) + 1
    por_canal = sorted(({"canal": k, "total": sum(v.values()),
                         "dominios": [{"dominio": d, "veces": n} for d, n in sorted(v.items(), key=lambda x: -x[1])]}
                        for k, v in canales.items()), key=lambda x: -x["total"])
    return {
        "dias": dias,
        "total": len(filas),
        "hoy": sum(1 for f in filas if f["t"] >= inicio_hoy),
        "por_canal": por_canal,
        "dominios": [{"dominio": d, "veces": n} for d, n in sorted(dominios.items(), key=lambda x: -x[1])],
        "ultimos": [{"hora": time.strftime("%d/%m %H:%M:%S", time.localtime(f["t"])), "dominio": f["dominio"],
                     "canal": f["canal"]} for f in sorted(filas, key=lambda x: -x["t"])[:50]],
    }
