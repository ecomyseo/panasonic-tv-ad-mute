"""
Panasonic Google TV Privacy Shield & Tracker Blocker
Bloquea la telemetría, el rastreo de audiencia de la TDT (HbbTV) y los envíos de datos fuera de casa.
"""

import os

import config
from tv_manager import PanasonicTVManager

# Solo dominios (un fichero hosts o Pi-hole no admite rutas ni comodines)
TRACKER_DOMAINS = [
    # Redes de publicidad dirigida de la TDT española (HbbTV / DVB-TA)
    "smartclip.net",
    "delivery.smartclip.net",
    "sunmedia.tv",
    "ad.sunmedia.tv",
    "hbbtv.atresmedia.com",
    "flashtalking.com",
    "scorecardresearch.com",   # Comscore, medición de audiencias TDT
    "sb.scorecardresearch.com",
    "imasdk.googleapis.com",

    # Telemetría de fabricantes y analíticas Smart TV
    "telemetry.panasonic.com",
    "connect.panasonic.biz",
    "device-metrics-us.amazon.com",
    "app-measurement.com",
    "google-analytics.com",
    "firebase-logging.admob.com"
]

PAQUETES_TELEMETRIA = [
    "com.google.android.feedback",
    "com.google.android.tv.feedbackconsent"
]


class PrivacyShield:
    def __init__(self, tv_ip=None):
        self.tv = PanasonicTVManager(tv_ip=tv_ip)
        self.tv_ip = self.tv.tv_ip

    def run_adb(self, cmd: str) -> str:
        return self.tv.adb(cmd)

    def enable_adguard_private_dns(self) -> str:
        """DNS privado (DoT) de AdGuard en la TV: filtra anuncios y rastreadores en todo el sistema."""
        self.tv.shell("settings", "put", "global", "private_dns_mode", "hostname")
        self.tv.shell("settings", "put", "global", "private_dns_specifier", "dns.adguard-dns.com")
        modo = self.tv.shell("settings", "get", "global", "private_dns_mode")
        if modo != "hostname":
            return "No se pudo activar el DNS privado (¿TV apagada o sin conexión ADB?)."
        return "DNS Privado AdGuard activado en la TV. Anuncios y telemetría bloqueados a nivel de sistema."

    def disable_private_dns(self) -> str:
        """Desactiva el DNS Privado y vuelve a la configuración por defecto."""
        self.tv.shell("settings", "put", "global", "private_dns_mode", "off")
        return "DNS Privado desactivado."

    def disable_telemetry_packages(self) -> list:
        """Desactiva paquetes de recopilación de métricas en Android TV (reversible)."""
        return [f"{pkg}: {self.tv.shell('pm', 'disable-user', '--user', '0', pkg) or 'sin respuesta'}"
                for pkg in PAQUETES_TELEMETRIA]

    def enable_telemetry_packages(self) -> list:
        """Vuelve a activar los paquetes desactivados."""
        return [f"{pkg}: {self.tv.shell('pm', 'enable', pkg) or 'sin respuesta'}" for pkg in PAQUETES_TELEMETRIA]

    def generate_hosts_blocklist(self, output_path=None) -> str:
        """Lista de bloqueo en formato hosts (Pi-hole, AdGuard Home o router)."""
        output_path = output_path or os.path.join(config.directorio_estado(), "tv_hosts_blocklist.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Bloqueador de telemetría TDT y Smart TV Panasonic\n")
            f.write("# Compatible con Pi-hole, AdGuard Home y routers (formato hosts)\n\n")
            for domain in TRACKER_DOMAINS:
                f.write(f"0.0.0.0 {domain}\n")
        return output_path
