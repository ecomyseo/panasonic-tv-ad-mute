#!/usr/bin/env python3
"""
Panasonic Google TV Control Suite - Menú interactivo
Compatible con Raspberry Pi Zero 2 W y Windows.
"""

import sys
import os
import time

# Asegurar importación de core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "core")))
from tv_manager import PanasonicTVManager
from media_info import MediaInfoService
from privacy_shield import PrivacyShield

TV_IP = os.getenv("TV_IP", "192.168.1.132:5555")
tv = PanasonicTVManager(tv_ip=TV_IP)
privacy = PrivacyShield(tv_ip=TV_IP)

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def banner():
    print("=" * 68)
    print("  PANASONIC GOOGLE TV SMART HUB & EPG (Raspberry Pi & Windows)")
    print(f"  Objetivo: {tv.tv_ip} | Canal actual: {tv.get_current_channel()}")
    print("=" * 68)

def menu_mando():
    while True:
        clear()
        banner()
        print("--- MANDO A DISTANCIA VIRTUAL ---")
        print(" [W] Arriba     [S] Abajo      [A] Izquierda   [D] Derecha")
        print(" [E] OK/Enter   [B] Volver     [H] Home        [P] Power (Standby)")
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
            tv.key_power()
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
        print(" 4. 🎮 Mando a distancia virtual (Cruceta, OK, Home, Back)")
        print(" 5. 🚀 Lanzador de Apps (YouTube, Netflix, Movistar+, TDT Live...)")
        print(" 6. ⌨️  Escribir texto / contraseñas en la TV desde teclado")
        print(" 7. ⏰ Temporizador de apagado inteligente (Sleep Timer)")
        print(" 8. 🧹 Acelerar y optimizar memoria RAM de la TV")
        print(" 9. 🌐 Iniciar Mando Web Móvil (puerto 8080)")
        print(" 0. Salir")
        print("=" * 68)
        op = input("Elige una opción: ").strip()

        if op == "1":
            print("\nSilenciando televisión...")
            tv.toggle_mute()
            time.sleep(1)
        elif op == "2":
            menu_privacidad()
        elif op == "3":
            menu_imdb()
        elif op == "4":
            menu_mando()
        elif op == "5":
            menu_apps()
        elif op == "6":
            escribir_texto()
        elif op == "7":
            sleep_timer_menu()
        elif op == "8":
            print("\nOptimizando memoria RAM...")
            res = tv.clean_ram()
            print(f"[OK] {res}")
            time.sleep(1.5)
        elif op == "9":
            web_script = os.path.join(os.path.dirname(__file__), "web_remote.py")
            os.system(f"python \"{web_script}\"")
        elif op == "0":
            break

if __name__ == "__main__":
    main()
