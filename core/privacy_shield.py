"""
Panasonic Google TV Privacy Shield & Tracker Blocker
Bloquea la telemetría, el rastreo de audiencia de la TDT (HbbTV) y los envíos de datos fuera de casa.
"""

import subprocess
import os

TRACKER_DOMAINS = [
    # Redes de publicidad dirigida de la TDT española (HbbTV / DVB-TA)
    "smartclip.net",
    "delivery.smartclip.net",
    "sunmedia.tv",
    "ad.sunmedia.tv",
    "hbbtv.atresmedia.com",
    "telecinco.es/hbbtv",
    "flashtalking.com",
    "scorecardresearch.com",   # Comscore medición de audiencias TDT
    "imasdk.googleapis.com",

    # Telemetría de fabricantes y analíticas Smart TV
    "telemetry.panasonic.com",
    "connect.panasonic.biz",
    "vestel.com/analytics",
    "device-metrics-us.amazon.com",
    "app-measurement.com",
    "google-analytics.com",
    "firebase-logging.admob.com"
]

class PrivacyShield:
    def __init__(self, tv_ip="192.168.1.132:5555"):
        self.tv_ip = tv_ip

    def run_adb(self, cmd: str) -> str:
        full_cmd = f"adb -s {self.tv_ip} {cmd}"
        try:
            res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=5)
            return res.stdout.strip()
        except Exception as e:
            return f"Error: {e}"

    def enable_adguard_private_dns(self) -> str:
        """
        Activa DNS Privado seguro (DoT) en Android TV mediante ADB.
        Filtra anuncios, rastreadores y telemetría a nivel de sistema operativo.
        """
        self.run_adb("shell settings put global private_dns_mode hostname")
        self.run_adb("shell settings put global private_dns_specifier dns.adguard-dns.com")
        return "DNS Privado AdGuard activado en la TV. Anuncios y telemetría bloqueados a nivel de sistema."

    def disable_private_dns(self) -> str:
        """Desactiva el DNS Privado y vuelve a la configuración por defecto."""
        self.run_adb("shell settings put global private_dns_mode off")
        return "DNS Privado desactivado."

    def disable_telemetry_packages(self) -> list:
        """Desactiva paquetes de recopilación de métricas y telemetría en Android TV."""
        packages = [
            "com.google.android.feedback",
            "com.google.android.tv.feedbackconsent"
        ]
        results = []
        for pkg in packages:
            out = self.run_adb(f"shell pm disable-user --user 0 {pkg}")
            results.append(f"{pkg}: {out}")
        return results

    def generate_hosts_blocklist(self, output_path="tv_hosts_blocklist.txt"):
        """Genera un archivo de bloqueo de dominios para Pi-hole o el archivo hosts del router."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Bloqueador de Telemetría TDT y Smart TV Panasonic\n")
            f.write("# Compatible con Pi-hole, AdGuard Home y Routers\n\n")
            for domain in TRACKER_DOMAINS:
                f.write(f"0.0.0.0 {domain}\n")
                f.write(f"0.0.0.0 *.{domain}\n")
        return output_path
