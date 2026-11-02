#!/usr/bin/env python3
"""
Herramienta de Diagnóstico y Compatibilidad de Televisores
Analiza la IP de un televisor y determina su compatibilidad con el sistema.
"""

import sys
import socket
import subprocess

def test_port(ip: str, port: int, timeout=1.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False

def diagnosticar_tv(ip: str):
    print("=" * 65)
    print(f" ANÁLISIS DE COMPATIBILIDAD DE TELEVISOR: {ip}")
    print("=" * 65)

    puertos = {
        5555:  ("ADB", "Android TV / Google TV / Fire OS (Control total nativo)"),
        6466:  ("Google Remote", "Android TV Remote Control Service"),
        8008:  ("Google Cast", "Chromecast integrado"),
        55000: ("Panasonic SOAP", "Panasonic My Home Screen / Viera"),
        8001:  ("Samsung Tizen", "Samsung Smart TV (WebSockets / SmartThings)"),
        3000:  ("LG webOS", "LG Smart TV (SSAP Pairing)")
    }

    abiertos = []
    for puerto, (nombre, desc) in puertos.items():
        if test_port(ip, puerto):
            print(f" [+] Puerto {puerto:5d} ABIERTO -> {nombre:16s} ({desc})")
            abiertos.append(puerto)
        else:
            print(f" [-] Puerto {puerto:5d} cerrado")

    print("\n" + "=" * 65)
    print(" RESULTADO DEL DIAGNÓSTICO:")
    print("=" * 65)

    if 5555 in abiertos:
        print(" -> NIVEL DE COMPATIBILIDAD: EXCELENTE (100% COMPATIBLE)")
        print("    Tu televisor tiene Android TV / Google TV con ADB activo.")
        print("    Todas las funciones están soportadas: silenciador automático,")
        print("    mando virtual, lanzador de apps, limpiador de RAM y sleep timer.\n")
        
        # Intentar consultar datos mediante ADB (lista de argumentos, sin shell)
        def adb(*args, timeout=6):
            try:
                return subprocess.run(["adb"] + list(args), capture_output=True, text=True, timeout=timeout).stdout
            except (OSError, subprocess.TimeoutExpired):
                return ""

        adb("connect", f"{ip}:5555", timeout=8)
        modelo = adb("-s", f"{ip}:5555", "shell", "getprop", "ro.product.model").strip()
        version = adb("-s", f"{ip}:5555", "shell", "getprop", "ro.build.version.release").strip()
        if modelo:
            print(f"    * Modelo identificado: {modelo}")
        if version:
            print(f"    * Versión de Android:  Android {version}")
        if not modelo:
            print("    * ADB no responde: acepta en la TV el aviso «¿Permitir depuración?» y repite.")

    elif 55000 in abiertos:
        print(" -> NIVEL DE COMPATIBILIDAD: COMPATIBLE (PANASONIC VIERA)")
        print("    Tu televisor es un Panasonic tradicional con sistema My Home Screen.")
        print("    Soporta control de volumen, Mute y teclas por la API SOAP.")

    elif 6466 in abiertos or 8008 in abiertos:
        print(" -> NIVEL DE COMPATIBILIDAD: ANDROID TV DETECTADO (REQUIERE ACTIVAR ADB)")
        print("    Tu televisor es Android TV / Google TV, pero el puerto 5555 (ADB)")
        print("    está apagado. Para activarlo:")
        print("    1. En la TV ve a Ajustes > Sistema > Información.")
        print("    2. Pulsa 7 veces sobre 'Compilación de Android TV'.")
        print("    3. En 'Opciones para desarrolladores', activa 'Depuración USB / Depuración por red'.")

    else:
        print(" -> AVISO: No se detectaron puertos de control conocidos.")
        print("    Asegúrate de que la televisión esté encendida y en la misma red Wi-Fi.")

if __name__ == "__main__":
    ip_tv = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.132"
    diagnosticar_tv(ip_tv)
