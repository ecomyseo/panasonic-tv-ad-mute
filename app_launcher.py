#!/usr/bin/env python3
"""
Panasonic Google TV Smart Hub para Windows.

Dos programas salen de aquí:

- PanasonicTVHub.exe (con consola): el menú. Si el hub ya está en marcha en segundo plano, solo
  enseña el menú; si no, arranca también el mando web y el servicio mientras esté abierto.
- PanasonicTVHubServicio.exe (sin ventana, servicio_windows.py): el hub en segundo plano.
    PanasonicTVHubServicio.exe --instalar      se copia a %LOCALAPPDATA%\\PanasonicTVHub, se apunta para
                                               arrancar al iniciar sesión en Windows y se pone en marcha
    PanasonicTVHubServicio.exe --desinstalar   lo para y lo quita del arranque

El mando solo atiende a este PC y a la red de casa. El estado (guía, recordatorios, canales
aprendidos) va a %APPDATA%\\PanasonicTVHub; la configuración, a un config.env junto al EXE o allí.
"""

import atexit
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

# ── Rutas de importacion: funciona como script y dentro del EXE de PyInstaller ──
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS            # carpeta temporal donde PyInstaller extrae todo
    JUNTO_AL_EXE = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    JUNTO_AL_EXE = BASE_DIR


def preparar_entorno():
    """Estado y configuración fuera de la carpeta temporal (antes de importar nada del hub)."""
    if not os.environ.get("STATE_DIR"):
        carpeta = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "PanasonicTVHub")
        os.makedirs(carpeta, exist_ok=True)
        os.environ["STATE_DIR"] = carpeta
    if not os.environ.get("TVHUB_CONFIG"):
        junto = os.path.join(JUNTO_AL_EXE, "config.env")
        os.environ["TVHUB_CONFIG"] = junto if os.path.isfile(junto) else os.path.join(os.environ["STATE_DIR"], "config.env")


preparar_entorno()
for carpeta in (os.path.join(BASE_DIR, 'raspberry_pi'), os.path.join(BASE_DIR, 'core'), BASE_DIR):
    sys.path.insert(0, carpeta)

import cortafuegos_windows  # noqa: E402
import estado  # noqa: E402
import menu_tv  # noqa: E402
import panasonic_ad_mute as servicio  # noqa: E402
import web_remote  # noqa: E402

STATE_DIR = os.environ["STATE_DIR"]
NOMBRE_SERVICIO = "PanasonicTVHubServicio.exe"
CLAVE_INICIO = os.environ.get("TVHUB_CLAVE_INICIO") or r"Software\Microsoft\Windows\CurrentVersion\Run"
VALOR_INICIO = "PanasonicTVHub"
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CERRADO = threading.Event()


def carpeta_instalacion():
    return (os.environ.get("TVHUB_DESTINO")
            or os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "PanasonicTVHub"))


def hub_en_marcha() -> bool:
    """¿Hay otro hub (el de segundo plano) atendiendo ya el mando y con el servicio vivo?"""
    return menu_tv.puerto_ocupado(web_remote.PORT) and estado.demonio_vivo()


def arrancar_hub(interactivo):
    """Servicio (silenciador, vuelta, avisos, recordatorios) + mando web + cortafuegos."""
    registro = os.path.join(STATE_DIR, "servicio.log")
    servicio.en_segundo_plano(registro=registro)
    atexit.register(servicio.cerrar)  # al salir, devuelve el sonido si lo había quitado
    threading.Thread(target=web_remote.main, daemon=True).start()

    def cortafuegos():
        # En cada arranque se comprueba la regla; solo si falta se crea (Windows pide permiso esa vez)
        if os.name != "nt" or os.environ.get("TVHUB_SIN_CORTAFUEGOS") == "1":
            return
        estado_fw, mensaje = cortafuegos_windows.asegurar(web_remote.PORT, STATE_DIR)
        if interactivo:
            print(("[OK] " if estado_fw != "no" else "[Aviso] ") + mensaje)
        else:
            servicio.log(mensaje)

    if interactivo:
        cortafuegos()
    else:
        threading.Thread(target=cortafuegos, daemon=True).start()  # el permiso no frena el arranque

    def vigilar_salida():
        # «--instalar» y «--desinstalar» piden así que se cierre el hub que esté en marcha
        estado.tomar_orden("salir")  # una orden vieja no lo cierra nada más arrancar
        while not estado.tomar_orden("salir"):
            time.sleep(1)
        servicio.log("Cerrando el hub (orden de salir).")
        servicio.cerrar()
        CERRADO.set()
        if interactivo:
            os._exit(0)

    threading.Thread(target=vigilar_salida, daemon=True).start()
    return registro


def abrir_navegador():
    time.sleep(1.5)
    if os.environ.get("TVHUB_SIN_NAVEGADOR") == "1":
        return
    try:
        webbrowser.open(f"http://localhost:{web_remote.PORT}")
    except Exception:  # noqa: BLE001
        pass


def main():
    """PanasonicTVHub.exe: el menú (y el hub, si no está ya en segundo plano)."""
    print("=" * 68)
    print("  PANASONIC GOOGLE TV SMART HUB  -  INICIANDO...")
    print("=" * 68)
    if hub_en_marcha():
        print("[OK] El hub ya está en marcha en segundo plano: este menú lo usa tal cual.")
    else:
        registro = arrancar_hub(interactivo=True)
        print(f"[OK] Registro del silenciador: {registro}")
        threading.Thread(target=abrir_navegador, daemon=True).start()
    print(f"[OK] En este equipo:        http://localhost:{web_remote.PORT}")
    print(f"[OK] En el móvil (en casa): http://{web_remote.LOCAL_IP}:{web_remote.PORT}")
    print("     Solo responde a este equipo y a la red de casa.")
    print("-" * 68)
    menu_tv.main()


# ======================================================== segundo plano
def _mensaje(texto):
    """Sin consola, el resultado de instalar o quitar se enseña en una ventanita."""
    with open(os.path.join(STATE_DIR, "instalacion.log"), "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {texto}\n")
    if os.environ.get("TVHUB_SIN_MENSAJES") != "1" and os.name == "nt":
        import ctypes  # noqa: PLC0415
        ctypes.windll.user32.MessageBoxW(0, texto, "Panasonic TV Hub", 0x40)


def _esperar(condicion, segundos):
    fin = time.time() + segundos
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.5)
    return condicion()


def parar_hub():
    """Pide al hub de segundo plano que se cierre (devuelve el sonido) y espera a que suelte el puerto."""
    if not menu_tv.puerto_ocupado(web_remote.PORT):
        return True
    estado.poner_orden("salir")
    return _esperar(lambda: not menu_tv.puerto_ocupado(web_remote.PORT), 30)


def _arrancar(ruta):
    if os.environ.get("TVHUB_ARRANQUE_DIRECTO") == "1":   # pruebas: con el entorno de quien lo lanza
        subprocess.Popen([ruta], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=SIN_VENTANA | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:  # como al iniciar sesión: lo arranca el escritorio de Windows, no este proceso
        subprocess.Popen(["explorer.exe", ruta], creationflags=SIN_VENTANA)


def instalar():
    if not getattr(sys, "frozen", False):
        _mensaje("Para instalarlo, ejecuta PanasonicTVHubServicio.exe --instalar.")
        return 1
    import winreg  # noqa: PLC0415
    if not parar_hub():
        _mensaje("No se ha podido parar el hub que estaba en marcha. Prueba otra vez en un minuto.")
        return 1
    carpeta = carpeta_instalacion()
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, NOMBRE_SERVICIO)
    if os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(os.path.abspath(destino)):
        for _ in range(20):  # el que se acaba de parar puede tardar en soltar el fichero
            try:
                shutil.copy2(sys.executable, destino)
                break
            except OSError:
                time.sleep(0.5)
        else:
            _mensaje(f"No se ha podido copiar el programa a {carpeta}.")
            return 1
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLAVE_INICIO) as clave:
        winreg.SetValueEx(clave, VALOR_INICIO, 0, winreg.REG_SZ, f'"{destino}"')
    _arrancar(destino)
    if _esperar(lambda: menu_tv.puerto_ocupado(web_remote.PORT), 60):
        _mensaje(f"Listo: Panasonic TV Hub arranca solo al iniciar Windows, sin ventanas.\n\n"
                 f"Ya está en marcha: http://localhost:{web_remote.PORT}\n"
                 f"En el móvil (en casa): http://{web_remote.LOCAL_IP}:{web_remote.PORT}")
        return 0
    _mensaje("Apuntado para arrancar con Windows, pero ahora no ha llegado a ponerse en marcha. "
             f"Mira {os.path.join(STATE_DIR, 'web.log')}.")
    return 1


def desinstalar():
    import winreg  # noqa: PLC0415
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLAVE_INICIO, 0, winreg.KEY_SET_VALUE) as clave:
            winreg.DeleteValue(clave, VALOR_INICIO)
    except OSError:
        pass
    parado = parar_hub()
    copia = os.path.join(carpeta_instalacion(), NOMBRE_SERVICIO)
    if os.path.normcase(os.path.abspath(sys.executable)) != os.path.normcase(os.path.abspath(copia)):
        for _ in range(20):
            try:
                if os.path.exists(copia):
                    os.remove(copia)
                break
            except OSError:
                time.sleep(0.5)
    _mensaje("Quitado del arranque de Windows." + ("" if parado else " (No se ha podido parar el que estaba en marcha.)"))
    return 0


def principal_servicio(argumentos):
    """PanasonicTVHubServicio.exe: sin ventana; lo que se imprima va a web.log."""
    if "--instalar" in argumentos:
        return instalar()
    if "--desinstalar" in argumentos:
        return desinstalar()
    salida = os.path.join(STATE_DIR, "web.log")
    if os.path.exists(salida) and os.path.getsize(salida) > 2 * 1024 * 1024:
        os.replace(salida, salida + ".1")
    sys.stdout = sys.stderr = open(salida, "a", encoding="utf-8", buffering=1)
    if hub_en_marcha():
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ya hay un hub en marcha: este no arranca.", flush=True)
        return 0
    arrancar_hub(interactivo=False)
    CERRADO.wait()
    return 0


if __name__ == "__main__":
    main()
