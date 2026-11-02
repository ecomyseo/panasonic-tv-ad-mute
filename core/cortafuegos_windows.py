"""
Cortafuegos de Windows para el mando web: el puerto abierto SOLO para la red de casa.

Al arrancar el programa de Windows se mira si existe la regla «Panasonic TV Hub (red de casa)» con el
puerto del mando y limitada a la subred local. Mirarla no necesita permisos. Solo si falta (o es de otro
puerto) se crea, y eso sí pide permiso de administrador: una vez, no en cada arranque.

TVHUB_NETSH y TVHUB_POWERSHELL sustituyen a netsh y powershell en las pruebas.
"""

import codecs
import os
import re
import shlex
import subprocess

REGLA = "Panasonic TV Hub (red de casa)"


def _orden(variable, defecto):
    return shlex.split(os.environ.get(variable) or defecto)


def _ejecutar(orden, timeout=120):
    try:
        res = subprocess.run(orden, capture_output=True, stdin=subprocess.DEVNULL, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    try:
        codecs.lookup("oem")
        cod = "oem"           # netsh escribe en la página de códigos de la consola
    except LookupError:
        cod = "utf-8"
    return res.returncode, (res.stdout or b"").decode(cod, "replace") + (res.stderr or b"").decode(cod, "replace")


def reglas(texto) -> list:
    """Bloques de 'netsh advfirewall firewall show rule' como diccionarios {campo: valor}. Los campos se
    quedan solo con las letras a-z («Acción» -> «accin»): según la página de códigos de la consola, la
    tilde puede llegar de cualquier manera."""
    bloques, actual = [], None
    for linea in texto.splitlines():
        if ":" not in linea:
            continue
        clave, valor = (p.strip() for p in linea.split(":", 1))
        clave = re.sub(r"[^a-z]", "", clave.lower())
        if clave in ("nombrederegla", "rulename"):
            actual = {"nombre": valor}
            bloques.append(actual)
        elif actual is not None:
            actual[clave] = valor
    return bloques


def regla_correcta(puerto, ejecutar=_ejecutar) -> bool:
    _, salida = ejecutar(_orden("TVHUB_NETSH", "netsh") + ["advfirewall", "firewall", "show", "rule", f"name={REGLA}"])
    for r in reglas(salida):
        activa = (r.get("habilitada") or r.get("enabled") or "").lower().startswith(("s", "y"))
        if (activa and r.get("localport") == str(puerto) and "localsubnet" in (r.get("remoteip") or "").lower()
                and (r.get("accin") or r.get("action") or "").lower().startswith(("perm", "allow"))):
            return True
    return False


def guion(puerto) -> str:
    return ("@echo off\r\n"
            f'netsh advfirewall firewall delete rule name="{REGLA}" >nul 2>&1\r\n'
            f'netsh advfirewall firewall add rule name="{REGLA}" dir=in action=allow protocol=TCP '
            f"localport={int(puerto)} remoteip=localsubnet profile=any >nul\r\n")


def asegurar(puerto, carpeta, ejecutar=_ejecutar):
    """Devuelve (estado, mensaje): 'ya' (estaba), 'hecho' (creada ahora) o 'no' (no se ha podido)."""
    if regla_correcta(puerto, ejecutar):
        return "ya", f"Cortafuegos: el puerto {puerto} está abierto solo para la red de casa."
    ruta = os.path.join(carpeta, "permitir_red_local.bat")
    with open(ruta, "w", encoding="ascii", newline="") as f:
        f.write(guion(puerto))
    ruta_ps = ruta.replace("'", "''")
    ejecutar(_orden("TVHUB_POWERSHELL", "powershell") + [
        "-NoProfile", "-Command", f"Start-Process -FilePath '{ruta_ps}' -Verb RunAs -WindowStyle Hidden -Wait"])
    if regla_correcta(puerto, ejecutar):
        return "hecho", f"Cortafuegos: abierto el puerto {puerto} solo para la red de casa."
    return "no", (f"Cortafuegos: no se ha podido abrir el puerto {puerto} (¿se ha cancelado el permiso?). "
                  "Este PC sí entra; el móvil, no hasta que se acepte.")
