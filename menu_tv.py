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

TV_IP = os.getenv("TV_IP", "192.168.1.132:5555")
tv = PanasonicTVManager(tv_ip=TV_IP)

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def banner():
    print("=" * 65)
    print("  PANASONIC GOOGLE TV CONTROL SUITE (Raspberry Pi & Windows)")
    print(f"  Objetivo: {tv.tv_ip} | Canal actual: {tv.get_current_channel()}")
    print("=" * 65)

def menu_mando():
    while True:
        clear()
        banner()
        print("--- MANDO A DISTANCIA VIRTUAL ---")
        print(" [W] Arriba     [S] Abajo      [A] Izquierda   [D] Derecha")
        print(" [E] OK/Enter   [B] Volver     [H] Home        [P] Power (Standby)")
        print(" [+] Vol +      [-] Vol -      [M] Mute        [Q] Volver al menú")
        print("-" * 65)
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
        print("-" * 65)
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
    print("Escribe lo que quieras (por ejemplo una búsqueda en YouTube o contraseña):")
    texto = input("> ").strip()
    if texto:
        tv.send_text(texto)
        print("\n[OK] Texto enviado directamente a la pantalla de la TV.")
        time.sleep(1.5)

def sleep_timer_menu():
    clear()
    banner()
    print("--- TEMPORIZADOR DE APAGADO (SLEEP TIMER) ---")
    print(" 1. Apagar en 15 minutos")
    print(" 2. Apagar en 30 minutos (con bajada gradual de volumen)")
    print(" 3. Apagar en 60 minutos (con bajada gradual de volumen)")
    print(" 4. Cancelar temporizador activo")
    print(" 0. Volver")
    print("-" * 65)
    op = input("Opción: ").strip()
    if op == "1":
        tv.start_sleep_timer(15, gradual=False)
        print("\n[OK] La tele se apagará en 15 minutos.")
    elif op == "2":
        tv.start_sleep_timer(30, gradual=True)
        print("\n[OK] Apagado en 30 minutos activado (atenuando volumen al final).")
    elif op == "3":
        tv.start_sleep_timer(60, gradual=True)
        print("\n[OK] Apagado en 60 minutos activado (atenuando volumen al final).")
    elif op == "4":
        tv.cancel_sleep_timer()
        print("\n[OK] Temporizador cancelado.")
    time.sleep(1.5)

def optimizar_tv():
    clear()
    banner()
    print("Optimizando memoria RAM y cerrando procesos secundarios en la TV...")
    res = tv.clean_ram()
    print(f"\n[OK] {res}")
    input("\nPresiona Enter para continuar...")

def ver_diagnostico():
    clear()
    banner()
    print("Consultando estado de la TV...")
    stats = tv.get_tv_stats()
    print("\n" + "-" * 40)
    print(f" Modelo TV:        {stats.get('model')}")
    print(f" Versión Android:  {stats.get('android_version')}")
    print(f" Canal TDT actual: {stats.get('channel')}")
    print(f" RAM Disponible:   {stats.get('ram_available')} / {stats.get('ram_total')}")
    print(f" Almacenamiento:   {stats.get('storage_data')}")
    print(f" Tiempo encendida: {stats.get('uptime')}")
    print("-" * 40)
    input("\nPresiona Enter para volver...")

def main():
    tv.connect()
    while True:
        clear()
        banner()
        print(" 1. 🔇 Silenciar / Modo Publicidad (150 segundos)")
        print(" 2. 🎮 Mando a distancia virtual (Cruceta, OK, Home, Back)")
        print(" 3. 🚀 Lanzador de Apps (YouTube, Netflix, Movistar+, TDT Live...)")
        print(" 4. ⌨️  Escribir texto / contraseñas en la TV")
        print(" 5. ⏰ Temporizador de apagado (Sleep Timer inteligente)")
        print(" 6. 🧹 Acelerar y optimizar memoria RAM de la TV")
        print(" 7. 📊 Diagnóstico y estado del televisor")
        print(" 8. 🌐 Iniciar Mando Web Móvil (puerto 8080)")
        print(" 0. Salir")
        print("=" * 65)
        op = input("Elige una opción: ").strip()

        if op == "1":
            print("\nSilenciando televisión...")
            tv.toggle_mute()
            time.sleep(1)
        elif op == "2":
            menu_mando()
        elif op == "3":
            menu_apps()
        elif op == "4":
            escribir_texto()
        elif op == "5":
            sleep_timer_menu()
        elif op == "6":
            optimizar_tv()
        elif op == "7":
            ver_diagnostico()
        elif op == "8":
            web_script = os.path.join(os.path.dirname(__file__), "web_remote.py")
            os.system(f"python \"{web_script}\"")
        elif op == "0":
            break

if __name__ == "__main__":
    main()
