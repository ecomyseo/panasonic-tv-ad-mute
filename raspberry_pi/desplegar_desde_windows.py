#!/usr/bin/env python3
"""
Instala o actualiza el Panasonic TV Hub en la Raspberry Pi desde Windows (o Linux / Mac) por SSH.

    python raspberry_pi/desplegar_desde_windows.py
    python raspberry_pi/desplegar_desde_windows.py --host raspberrypi.local --usuario pi --tv-ip 192.168.1.132

Sin argumentos pregunta lo necesario. Pasos:
  1. Empaqueta el proyecto (solo lo que se instala; sin .git, ejecutables ni cachés) y, si está
     configurado, el módulo privado de WhatsApp (../mensajero_whatsapp_privado) como privado/.
  2. Lo envía por SSH a ~/panasonic-tv-hub-src en la Raspberry. Si tienes clave SSH, la deja
     autorizada para que las siguientes veces no pida contraseña.
  3. Ejecuta allí: sudo bash raspberry_pi/install.sh

Usa el cliente OpenSSH (ssh), que ya viene con Windows 10 y 11.
--solo-paquete FICHERO.tar.gz  genera el paquete y no se conecta a nada.
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIVADO = os.path.join(os.path.dirname(REPO), "mensajero_whatsapp_privado")
INCLUIR = ["core", "raspberry_pi", "avisos_app/TVHubAvisos.apk", "web_remote.py", "menu_tv.py", "README.md", "COMPATIBILIDAD.md", "LICENSE"]
EXCLUIR_DIRS = {"__pycache__", ".estado", ".git"}
EJECUTABLES = {"install.sh", "uninstall.sh", "tvhub", "panasonic_ad_mute.py", "web_remote.py", "menu_tv.py",
               "epg.py", "detectar_tv.py", "desplegar_desde_windows.py"}
TEXTO = (".py", ".sh", ".service", ".env", ".md", ".txt", ".json", "")
DESTINO_REMOTO = "panasonic-tv-hub-src"


def _añadir(tar, ruta, nombre):
    with open(ruta, "rb") as f:
        datos = f.read()
    base = os.path.basename(ruta)
    if os.path.splitext(base)[1] in TEXTO and b"\0" not in datos:
        datos = datos.replace(b"\r\n", b"\n")  # bash y python en la Raspberry no quieren CRLF
    info = tarfile.TarInfo(nombre)
    info.size = len(datos)
    info.mode = 0o755 if base in EJECUTABLES else 0o644
    tar.addfile(info, io.BytesIO(datos))


def whatsapp_configurado() -> bool:
    creds = os.path.join(PRIVADO, "credenciales_privadas.json")
    if not (os.path.isfile(os.path.join(PRIVADO, "mensajero_tv.py")) and os.path.isfile(creds)):
        return False
    try:
        with open(creds, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (OSError, ValueError):
        return False
    return bool(datos.get("API_KEY")) and "TU_API_KEY" not in datos["API_KEY"] and datos.get("TELEFONO_DESTINO") not in ("", "34600000000")


def clave_publica():
    for nombre in ("id_ed25519.pub", "id_ecdsa.pub", "id_rsa.pub"):
        ruta = os.path.join(os.path.expanduser("~"), ".ssh", nombre)
        if os.path.isfile(ruta):
            with open(ruta, "rb") as f:
                return f.read().strip() + b"\n"
    return None


def construir_paquete(con_whatsapp: bool) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for elemento in INCLUIR:
            origen = os.path.join(REPO, elemento)
            if os.path.isfile(origen):
                _añadir(tar, origen, elemento)
            elif os.path.isdir(origen):
                for raiz, dirs, ficheros in os.walk(origen):
                    dirs[:] = sorted(d for d in dirs if d not in EXCLUIR_DIRS)
                    for fichero in sorted(ficheros):
                        if fichero.endswith((".pyc", ".pyo")):
                            continue
                        ruta = os.path.join(raiz, fichero)
                        _añadir(tar, ruta, os.path.relpath(ruta, REPO).replace(os.sep, "/"))
        if con_whatsapp:
            for fichero in ("mensajero_tv.py", "credenciales_privadas.json"):
                _añadir(tar, os.path.join(PRIVADO, fichero), "privado/" + fichero)
        clave = clave_publica()
        if clave:
            info = tarfile.TarInfo("_clave_ssh.pub")
            info.size = len(clave)
            tar.addfile(info, io.BytesIO(clave))
    return buf.getvalue()


def preguntar(texto, defecto):
    try:
        valor = input(f"{texto} [{defecto}]: ").strip()
    except EOFError:
        valor = ""
    return valor or defecto


def main():
    ap = argparse.ArgumentParser(description="Instala el Panasonic TV Hub en la Raspberry Pi por SSH")
    ap.add_argument("--host", help="Nombre o IP de la Raspberry (raspberrypi.local)")
    ap.add_argument("--usuario", help="Usuario SSH de la Raspberry (pi)")
    ap.add_argument("--tv-ip", help="IP de la TV (si se omite se conserva la configurada)")
    ap.add_argument("--tv-mac", help="MAC de la TV para encenderla por la red")
    ap.add_argument("--sin-whatsapp", action="store_true", help="No enviar el módulo privado de WhatsApp")
    ap.add_argument("--solo-paquete", metavar="FICHERO", help="Solo genera el .tar.gz")
    args = ap.parse_args()

    con_whatsapp = not args.sin_whatsapp and whatsapp_configurado()
    paquete = construir_paquete(con_whatsapp)

    if args.solo_paquete:
        with open(args.solo_paquete, "wb") as f:
            f.write(paquete)
        print(f"Paquete: {args.solo_paquete} ({len(paquete) // 1024} KB, WhatsApp: {'sí' if con_whatsapp else 'no'})")
        return 0

    ssh = shutil.which("ssh")
    if not ssh:
        print("No encuentro 'ssh'. En Windows: Configuración > Aplicaciones > Características opcionales > Cliente OpenSSH.")
        return 1

    interactivo = sys.stdin.isatty() and not args.host
    host = args.host or (preguntar("Raspberry Pi (nombre o IP)", "raspberrypi.local") if interactivo else "raspberrypi.local")
    usuario = args.usuario or (preguntar("Usuario de la Raspberry", "pi") if interactivo else "pi")
    tv_ip = args.tv_ip or (preguntar("IP de la TV (Enter = la que ya tenga configurada)", "") if interactivo else "")
    destino = f"{usuario}@{host}"
    opciones = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"]

    print(f"\n[1/2] Enviando {len(paquete) // 1024} KB a {destino} "
          f"(WhatsApp: {'sí' if con_whatsapp else 'no'})...")
    remoto = (
        f"set -e; rm -rf ~/{DESTINO_REMOTO}; mkdir -p ~/{DESTINO_REMOTO}; tar xzf - -C ~/{DESTINO_REMOTO}; "
        f"if [ -f ~/{DESTINO_REMOTO}/_clave_ssh.pub ]; then mkdir -p ~/.ssh; chmod 700 ~/.ssh; "
        f"touch ~/.ssh/authorized_keys; grep -qxF \"$(cat ~/{DESTINO_REMOTO}/_clave_ssh.pub)\" ~/.ssh/authorized_keys "
        f"|| cat ~/{DESTINO_REMOTO}/_clave_ssh.pub >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys; "
        f"rm -f ~/{DESTINO_REMOTO}/_clave_ssh.pub; fi; echo PAQUETE_RECIBIDO"
    )
    res = subprocess.run([ssh] + opciones + [destino, remoto], input=paquete, stdout=subprocess.PIPE)
    salida = res.stdout.decode("utf-8", "replace")
    if res.returncode != 0 or "PAQUETE_RECIBIDO" not in salida:
        print(f"No se pudo enviar el paquete (código {res.returncode}). Comprueba el nombre, el usuario y que SSH esté activado.")
        return 1

    instalar = f"sudo bash ~/{DESTINO_REMOTO}/raspberry_pi/install.sh"
    if tv_ip:
        instalar += f" --tv-ip {tv_ip}"
    if args.tv_mac:
        instalar += f" --tv-mac {args.tv_mac}"
    instalar += f"; codigo=$?; rm -rf ~/{DESTINO_REMOTO}/privado; exit $codigo"
    print("[2/2] Instalando en la Raspberry...\n")
    res = subprocess.run([ssh, "-t"] + opciones + [destino, instalar])
    if res.returncode != 0:
        print(f"\nLa instalación terminó con errores (código {res.returncode}). Revisa los mensajes de arriba.")
        return res.returncode
    print(f"\nListo. Abre en el móvil: http://{host}:8080")
    return 0


if __name__ == "__main__":
    sys.exit(main())
