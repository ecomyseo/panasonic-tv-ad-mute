#!/usr/bin/env python3
"""
Panasonic TV Hub en segundo plano para Windows (PanasonicTVHubServicio.exe, sin ventana).

    PanasonicTVHubServicio.exe                 el hub: mando web, silenciador, avisos y recordatorios
    PanasonicTVHubServicio.exe --instalar      arrancar solo al iniciar Windows (y ponerlo en marcha ya)
    PanasonicTVHubServicio.exe --desinstalar   quitarlo del arranque y pararlo
"""

import sys

import app_launcher

if __name__ == "__main__":
    sys.exit(app_launcher.principal_servicio(sys.argv[1:]))
