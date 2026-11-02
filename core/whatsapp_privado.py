"""
Módulo privado de WhatsApp (mensajero_tv.py), que no va en el repositorio.

Se busca en <base>/privado (Raspberry) o en ../mensajero_whatsapp_privado (copia de trabajo).
Devuelve (módulo, credenciales) o None si no está o tiene los valores de ejemplo.
"""

import os
import sys


def cargar(base):
    if os.environ.get("TVHUB_SIN_WHATSAPP") == "1":
        return None
    for carpeta in (os.path.join(base, "privado"), os.path.join(base, "..", "mensajero_whatsapp_privado")):
        if not os.path.isfile(os.path.join(carpeta, "mensajero_tv.py")):
            continue
        if carpeta not in sys.path:
            sys.path.insert(0, carpeta)
        try:
            import mensajero_tv  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            return None
        creds = mensajero_tv.cargar_credenciales()
        clave, tel = creds.get("API_KEY", ""), creds.get("TELEFONO_DESTINO", "")
        if not clave or "TU_API_KEY" in clave or not tel or tel == "34600000000":
            return None
        return mensajero_tv, creds
    return None
