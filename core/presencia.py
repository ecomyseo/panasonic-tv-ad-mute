"""
¿Está el móvil en casa? (un ping a su IP) y la MAC de la tele (de la tabla ARP), para encenderla por red.
Sin instalar nada: el ping y la tabla ARP del sistema.
"""

import os
import re
import subprocess

SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _correr(orden, timeout=6) -> str:
    try:
        r = subprocess.run(orden, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=timeout,
                           encoding="utf-8", errors="replace", creationflags=SIN_VENTANA)
        return (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def responde(ip: str, intentos=2) -> bool:
    """Ping. Se mira «TTL=» en la respuesta: en Windows, «host inaccesible» sale con código 0."""
    if not ip:
        return False
    for _ in range(max(1, intentos)):
        if os.name == "nt":
            salida = _correr(["ping", "-n", "1", "-w", "1500", ip])
        else:
            salida = _correr(["ping", "-c", "1", "-W", "2", ip])
        if "ttl=" in salida.lower():
            return True
    return False


def mac_de(ip: str) -> str:
    """MAC de una IP de la red de casa según la tabla ARP ('' si no está)."""
    if not ip:
        return ""
    ip = ip.split(":")[0]
    if os.name == "nt":
        salida = _correr(["arp", "-a", ip])
    else:
        try:
            with open("/proc/net/arp", encoding="ascii") as f:
                salida = f.read()
        except OSError:
            salida = _correr(["ip", "neigh", "show", ip])
    for linea in salida.splitlines():
        if re.search(rf"(^|\s){re.escape(ip)}(\s|$)", linea):
            m = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", linea)
            if m and m.group(0).replace("-", ":").lower() != "00:00:00:00:00:00":
                return m.group(0).replace("-", ":").lower()
    return ""
