#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Panasonic Google TV Control Suite - Menu interactivo
Compatible con Raspberry Pi Zero 2 W y Windows.
"""

import sys
import os
import time

# Fix encoding para Windows (terminal cp1252 no soporta emojis sin esto)
if sys.platform == 'win32' and sys.stdout is not None:  # sin consola (servicio en segundo plano) no hay nada que ajustar
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Asegurar importacion de core
if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
else:
    _base = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _base)
sys.path.insert(0, os.path.join(_base, 'core'))

import atexit  # noqa: E402
import socket  # noqa: E402

import config  # noqa: E402
import estado  # noqa: E402
from tv_manager import PanasonicTVManager  # noqa: E402
from media_info import MediaInfoService  # noqa: E402
from privacy_shield import PrivacyShield  # noqa: E402

CFG = config.cargar()
TV_IP = CFG["TV_IP"]
MUTE_DURATION = config.entero(CFG, "MUTE_DURATION", 150)
tv = PanasonicTVManager(tv_ip=TV_IP)
privacy = PrivacyShield(tv_ip=TV_IP)


@atexit.register
def _al_salir():
    # Si este menú quitó el sonido, lo devuelve al cerrarse
    if tv.silenciada_por_nosotros:
        tv.restaurar()


def puerto_ocupado(puerto: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        return s.connect_ex(("127.0.0.1", puerto)) == 0
    finally:
        s.close()

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def banner():
    print("=" * 68)
    print("  PANASONIC GOOGLE TV SMART HUB & EPG (Raspberry Pi & Windows)")
    d = estado.leer()
    canal = d.get("canal") if estado.demonio_vivo(d) and d.get("canal") else tv.get_current_channel().get("name", "?")
    auto = "en pausa" if estado.pausado() else ("activo" if estado.demonio_vivo(d) else "parado")
    print(f"  TV: {tv.tv_ip} | Canal: {canal} | Silenciador automático: {auto}")
    print("=" * 68)

def menu_mando():
    while True:
        clear()
        banner()
        print("--- MANDO A DISTANCIA VIRTUAL ---")
        print(" [W] Arriba     [S] Abajo      [A] Izquierda   [D] Derecha")
        print(" [E] OK/Enter   [B] Volver     [H] Home        [P] Apagar (standby)")
        print(" [+] Vol +      [-] Vol -      [M] Mute        [Q] Volver al menú")
        print("-" * 68)
        tecla = input("Pulsa una tecla y Enter: ").strip().lower()
        if tecla == "q":
            break
        elif tecla == "w":
            tv.key_dpad("up")
        elif tecla == "s":
            tv.key_dpad("down")
        elif tecla == "a":
            tv.key_dpad("left")
        elif tecla == "d":
            tv.key_dpad("right")
        elif tecla == "e":
            tv.key_dpad("enter")
        elif tecla == "b":
            tv.key_back()
        elif tecla == "h":
            tv.key_home()
        elif tecla == "p":
            tv.apagar()
        elif tecla in ("+", "v+"):
            tv.volume_up()
        elif tecla in ("-", "v-"):
            tv.volume_down()
        elif tecla == "m":
            tv.toggle_mute()

def menu_privacidad():
    clear()
    banner()
    print("--- 🛡️ ESCUDO DE PRIVACIDAD Y BLOQUEO DE TELEMETRÍA ---")
    print(" 1. Activar DNS Privado AdGuard en la TV (Bloqueo a nivel SO)")
    print(" 2. Desactivar paquetes de analíticas y telemetría por ADB")
    print(" 3. Generar lista de dominios de rastreo TDT para Pi-hole")
    print(" 4. Desactivar DNS Privado y volver al modo normal")
    print(" 0. Volver")
    print("-" * 68)
    op = input("Elige una opción: ").strip()
    if op == "1":
        res = privacy.enable_adguard_private_dns()
        print(f"\n[OK] {res}")
    elif op == "2":
        res = privacy.disable_telemetry_packages()
        print("\n[OK] Paquetes desactivados:")
        for r in res:
            print(f"  - {r}")
    elif op == "3":
        f = privacy.generate_hosts_blocklist()
        print(f"\n[OK] Archivo generado con éxito en: {f}")
    elif op == "4":
        res = privacy.disable_private_dns()
        print(f"\n[OK] {res}")
    input("\nPresiona Enter para continuar...")

def menu_imdb():
    clear()
    banner()
    print("--- 🎬 CONSULTA DE FICHA IMDB / FILMAFFINITY ---")
    titulo = input("Introduce el título de la película o programa: ").strip()
    if titulo:
        print("\nConsultando bases de datos de cine...")
        info = MediaInfoService.buscar_info_pelicula(titulo)
        print("\n" + "=" * 50)
        print(f" Título:      {info['title']} ({info['year']})")
        print(f" Valoración:  {info['rating']}")
        print(f" Director:    {info['director']}")
        print(f" Distintivo:  {info['badge']}")
        print("-" * 50)
        print(f" Sinopsis:\n {info['synopsis']}")
        print("=" * 50)
    input("\nPresiona Enter para continuar...")

def menu_apps():
    apps = tv.get_known_apps()
    while True:
        clear()
        banner()
        print("--- LANZADOR DE APLICACIONES ---")
        keys = list(apps.keys())
        for idx, name in enumerate(keys, 1):
            print(f" {idx}. {name}")
        print(" 0. Volver")
        print("-" * 68)
        op = input("Elige la app para abrir en la TV: ").strip()
        if op == "0":
            break
        if op.isdigit() and 1 <= int(op) <= len(keys):
            app_sel = keys[int(op) - 1]
            print(f"\nAbriendo {app_sel}...")
            tv.launch_app(app_sel)
            time.sleep(1.5)

def escribir_texto():
    clear()
    banner()
    print("--- ESCRIBIR TEXTO O BUSCAR EN LA TV ---")
    texto = input("Escribe lo que quieras enviar a la pantalla de la TV: ").strip()
    if texto:
        tv.send_text(texto)
        print("\n[OK] Texto enviado directamente a la TV.")
        time.sleep(1.5)

def sleep_timer_menu():
    clear()
    banner()
    print("--- TEMPORIZADOR DE APAGADO (SLEEP TIMER) ---")
    print(" 1. Apagar en 15 minutos")
    print(" 2. Apagar en 30 minutos (con atenuación gradual de volumen)")
    print(" 3. Apagar en 60 minutos (con atenuación gradual de volumen)")
    print(" 4. Cancelar temporizador activo")
    print(" 0. Volver")
    print("-" * 68)
    op = input("Opción: ").strip()
    if op == "1":
        tv.start_sleep_timer(15, gradual=False)
        print("\n[OK] Apagado en 15 minutos activado.")
    elif op == "2":
        tv.start_sleep_timer(30, gradual=True)
        print("\n[OK] Apagado en 30 minutos activado con volumen decreciente.")
    elif op == "3":
        tv.start_sleep_timer(60, gradual=True)
        print("\n[OK] Apagado en 60 minutos activado con volumen decreciente.")
    elif op == "4":
        tv.cancel_sleep_timer()
        print("\n[OK] Temporizador cancelado.")
    time.sleep(1.5)

def main():
    tv.connect()
    while True:
        clear()
        banner()
        print(" 1. 🔇 Silenciar / Modo Publicidad (150 segundos)")
        print(" 2. 🛡️  Escudo de Privacidad (Bloquear telemetría y rastreo TDT)")
        print(" 3. 🎬 Consulta de Ficha IMDb / Filmaffinity y notas")
        print(" 4. 📺 Proyectar Banner con Botón Especial en la pantalla de la TV")
        print(" 5. 🎮 Mando a distancia virtual (Cruceta, OK, Home, Back)")
        print(" 6. 🚀 Lanzador de Apps (YouTube, Netflix, Movistar+, TDT Live...)")
        print(" 7. ⌨️  Escribir texto / contraseñas en la TV desde teclado")
        print(" 8. ⏰ Temporizador de apagado inteligente (Sleep Timer)")
        print(" 9. 🧹 Acelerar y optimizar memoria RAM de la TV")
        print(" 10. 🌐 Mando web para el móvil")
        print(" 11. ⏯  Pausar / reanudar el silenciador automático")
        print(" 12. ⏻  Encender / apagar la TV")
        print(" 0. Salir")
        print("=" * 68)
        op = input("Elige una opción: ").strip()

        if op == "1":
            if estado.demonio_vivo():
                estado.poner_orden("silenciar")
                print(f"\n[OK] El servicio silencia la TV durante {MUTE_DURATION} s.")
            elif tv.silenciar_temporal(MUTE_DURATION):
                print(f"\n[OK] TV silenciada {MUTE_DURATION} s (el sonido vuelve solo; no cierres el menú).")
            else:
                print("\n[Aviso] La TV ya estaba silenciada.")
            time.sleep(1.5)
        elif op == "2":
            menu_privacidad()
        elif op == "3":
            menu_imdb()
        elif op == "4":
            titulo = input("Título a proyectar en la TV [Vacío para Inception]: ").strip()
            peli = titulo if titulo else "Inception"
            print(f"\nProyectando banner de '{peli}' en la pantalla de la televisión...")
            res = tv.show_banner_on_tv(title=peli, duration=8)
            print(f"[OK] {res}")
            time.sleep(1.5)
        elif op == "5":
            menu_mando()
        elif op == "6":
            menu_apps()
        elif op == "7":
            escribir_texto()
        elif op == "8":
            sleep_timer_menu()
        elif op == "9":
            print("\nOptimizando memoria RAM...")
            res = tv.clean_ram()
            print(f"[OK] {res}")
            time.sleep(1.5)
        elif op == "10":
            puerto = config.entero(CFG, "WEB_PORT", 8080)
            if puerto_ocupado(puerto):
                print(f"\n[OK] El mando web ya está en marcha: abre http://<IP de este equipo>:{puerto} en el móvil.")
                input("\nPresiona Enter para continuar...")
            else:
                import web_remote
                web_remote.main()
        elif op == "11":
            estado.pausar(not estado.pausado())
            print("\n[OK] Silenciador automático " + ("en pausa." if estado.pausado() else "activo."))
            time.sleep(1.5)
        elif op == "12":
            enc = tv.esta_encendida()
            print("\n" + (tv.apagar() if enc else tv.encender()))
            time.sleep(1.5)
        elif op == "0":
            break

if __name__ == "__main__":
    main()
