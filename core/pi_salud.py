"""
Salud de la Raspberry Pi: temperatura, falta de alimentación (muy típico si se
alimenta desde el USB de la TV), carga, memoria y tiempo encendida.
En un equipo que no es una Raspberry devuelve lo que pueda leer.
"""

import os
import shutil
import subprocess
import time

BITS_THROTTLED = {
    0x1: "Tensión baja AHORA",
    0x2: "Frecuencia limitada AHORA",
    0x4: "CPU frenada AHORA",
    0x8: "Límite de temperatura AHORA",
    0x10000: "Ha habido tensión baja",
    0x20000: "Ha habido frecuencia limitada",
    0x40000: "Ha habido CPU frenada",
    0x80000: "Ha habido límite de temperatura",
}


def _leer(ruta):
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            return f.read().strip().strip("\x00")
    except OSError:
        return ""


def leer() -> dict:
    datos = {"modelo": _leer("/sys/firmware/devicetree/base/model") or "",
             "temperatura": None, "alimentacion": [], "alimentacion_ok": None,
             "carga": None, "ram_libre_mb": None, "ram_total_mb": None, "encendida_horas": None}

    getprop = shutil.which("getprop")
    if getprop and os.environ.get("PREFIX", "").startswith("/data/data/com.termux"):
        # En un móvil con Termux: marca y modelo del teléfono (el árbol de dispositivos no se deja leer)
        try:
            partes = [subprocess.run([getprop, p], capture_output=True, text=True, timeout=3,
                                     stdin=subprocess.DEVNULL).stdout.strip()
                      for p in ("ro.product.manufacturer", "ro.product.model", "ro.build.version.release")]
            if partes[1]:
                datos["modelo"] = f"{partes[0]} {partes[1]} (Android {partes[2]})".strip()
        except (OSError, subprocess.SubprocessError):
            pass

    t = _leer("/sys/class/thermal/thermal_zone0/temp")
    if t.isdigit():
        datos["temperatura"] = round(int(t) / 1000.0, 1)

    vcgencmd = shutil.which("vcgencmd")
    if vcgencmd:
        try:
            out = subprocess.run([vcgencmd, "get_throttled"], capture_output=True, text=True, timeout=3,
                                 stdin=subprocess.DEVNULL).stdout
            valor = int(out.strip().split("=")[1], 16)
            datos["alimentacion"] = [texto for bit, texto in BITS_THROTTLED.items() if valor & bit]
            datos["alimentacion_ok"] = valor == 0
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            pass

    if hasattr(os, "getloadavg"):
        try:
            datos["carga"] = round(os.getloadavg()[0], 2)
        except OSError:
            pass

    for linea in _leer("/proc/meminfo").splitlines():
        if linea.startswith("MemTotal:"):
            datos["ram_total_mb"] = int(linea.split()[1]) // 1024
        elif linea.startswith("MemAvailable:"):
            datos["ram_libre_mb"] = int(linea.split()[1]) // 1024

    up = _leer("/proc/uptime").split()
    if up:
        try:
            datos["encendida_horas"] = round(float(up[0]) / 3600, 1)
        except ValueError:
            pass
    datos["leido"] = time.time()
    return datos
