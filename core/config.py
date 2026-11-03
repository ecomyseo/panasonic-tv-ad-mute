"""
Configuración común del Panasonic TV Hub.

Orden de carga (lo último gana):
  1. Valores por defecto de este fichero.
  2. raspberry_pi/config.env del propio proyecto (plantilla).
  3. /etc/panasonic-tv-hub/config.env (instalación en la Raspberry Pi).
  4. Variables de entorno con el mismo nombre.
"""

import os
import shlex

RAIZ_PROYECTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PLANTILLA = os.path.join(RAIZ_PROYECTO, "raspberry_pi", "config.env")
CONFIG_SISTEMA = os.environ.get("TVHUB_CONFIG", "/etc/panasonic-tv-hub/config.env")
ESTADO_SISTEMA = "/var/lib/panasonic-tv-hub"

DEFECTOS = {
    "TV_IP": "192.168.1.132:5555",
    "TV_MAC": "",
    "ADB_BIN": "adb",
    "WEB_PORT": "8080",
    "WEB_NOMBRES_PERMITIDOS": "",
    "MUTE_DURATION": "150",
    "COOLDOWN_SECONDS": "30",
    "AD_PATTERNS": "",  # los de antes salen cada 30 s haya anuncios o no (medido el 2026-11-02)
    "LOGCAT_TAGS": "MtkTvHBBTVBase:D,AUDIO_AMP:W,MtkTvChannelList_jni:D",
    "AD_END_PATTERNS": "",
    "VOLVER_AL_CANAL": "1",
    "DURACION_PUBLI": "300",
    "AVISOS_EN_TV": "1",
    "TVOVERLAY_URL": "",
    "AVISOS_DURACION": "8",
    "AVISOS_TAMANO": "40",
    "AVISOS_POSICION": "centro",
    "RECORDATORIO_ANTELACION": "60",
    "MODO_APRENDIZAJE": "0",
    "FICHA_AL_CAMBIAR": "1",  # ficha de lo que echan la primera vez que llegas a ese programa
    "FICHA_ESPERA": "3",
    "FICHA_SEGUNDOS": "10",
    "VOLUMEN_CADA": "20",         # además de al tocar el volumen en el mando: cada cuántos segundos se mira
    "VOLUMEN_ESTABLE": "8",
    "VOLUMEN_TRAS_CAMBIO": "10",
    "DNS_ACTIVO": "0",        # 1 = el hub hace de DNS antirrastreo (pensado para la Raspberry)
    "DNS_PUERTO": "53",
    "DNS_SUPERIOR": "1.1.1.1",
    "GUIA_SILENCIA": "0",    # 1 = silenciar con la señal de la guía (sin confirmar: de fábrica solo se apunta)
    "GUIA_TRAS_ZAPEO": "20",
    "GUIA_CALMA": "480",
    "APAGADO_NOCTURNO": "",
    "EPG_URL": "https://raw.githubusercontent.com/davidmuma/EPG_dobleM/master/guiatv_sincolor.xml.gz",
    "EPG_HORAS_REFRESCO": "4",
    "TMDB_API_KEY": "",
    "STATE_DIR": "",
}


def _leer_env(ruta, destino):
    if not ruta or not os.path.isfile(ruta):
        return
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                destino[clave.strip()] = valor.strip().strip('"').strip("'")
    except OSError:
        pass


def cargar() -> dict:
    cfg = dict(DEFECTOS)
    _leer_env(CONFIG_PLANTILLA, cfg)
    _leer_env(CONFIG_SISTEMA, cfg)
    for clave in list(cfg.keys()):
        if clave in os.environ:
            cfg[clave] = os.environ[clave]
    cfg["TV_IP"] = normalizar_ip(cfg.get("TV_IP", ""))
    return cfg


def normalizar_ip(ip: str) -> str:
    ip = (ip or "").strip()
    if ip and ":" not in ip:
        ip += ":5555"
    return ip


def entero(cfg: dict, clave: str, defecto: int) -> int:
    try:
        return int(str(cfg.get(clave, defecto)).strip())
    except (TypeError, ValueError):
        return defecto


def lista(cfg: dict, clave: str) -> list:
    return [p.strip() for p in str(cfg.get(clave, "")).split(",") if p.strip()]


def adb_bin(cfg: dict) -> list:
    """Orden de ADB como lista (admite 'python /ruta/falso_adb.py' para pruebas)."""
    partes = shlex.split(cfg.get("ADB_BIN") or "adb")
    return partes or ["adb"]


def directorio_estado(cfg: dict = None) -> str:
    """Carpeta compartida entre el silenciador, el mando web y el menú."""
    cfg = cfg or cargar()
    candidatos = [cfg.get("STATE_DIR", ""), os.environ.get("STATE_DIRECTORY", "").split(":")[0]]
    if os.path.isdir(ESTADO_SISTEMA) and os.access(ESTADO_SISTEMA, os.W_OK):
        candidatos.append(ESTADO_SISTEMA)
    candidatos.append(os.path.join(RAIZ_PROYECTO, ".estado"))
    for ruta in candidatos:
        if not ruta:
            continue
        try:
            os.makedirs(ruta, exist_ok=True)
            if os.access(ruta, os.W_OK):
                return ruta
        except OSError:
            continue
    return RAIZ_PROYECTO
