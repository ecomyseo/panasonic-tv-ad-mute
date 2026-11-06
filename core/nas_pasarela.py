"""
Pasarela del NAS para fuera de casa, pensada para el móvil del hub (Termux):

- SFTP cifrado: «rclone serve sftp» sobre el FTP del disco USB del router. Desde fuera solo se ve
  el SFTP (SSH); el FTP, que viaja sin cifrar, se queda dentro de casa.
- Nombre fijo: avisa a DuckDNS de la IP de casa cada 10 minutos, para que «<nombre>.duckdns.org»
  siga apuntando aquí aunque Digi cambie la IP.
- Entrada aparte para los servidores que mandan copias (otro puerto): solo con clave SSH, sin contraseña, y
  con la raíz en <carpeta>/servidores, de modo que un servidor asaltado no puede ver ni borrar el resto del
  disco (por ejemplo la copia del PC). Sus claves van en otro fichero y no sirven en la entrada principal.

La configuración lleva claves y vive en la carpeta de estado (nas.json, permisos 600), nunca en el
repositorio: se manda desde el PC de casa con POST /api/nas del mando web. Lo que se enseña
(nas_estado.json y GET /api/nas) no lleva ninguna clave.

Se ejecuta aparte (termux/arrancar.sh la vigila): python core/nas_pasarela.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import estado  # noqa: E402

DUCKDNS_URL = os.environ.get("TVHUB_DUCKDNS_URL", "https://www.duckdns.org/update")
# La orden de rclone como lista JSON (las pruebas ponen aquí un rclone de mentira)
RCLONE = json.loads(os.environ.get("TVHUB_RCLONE_ORDEN") or '["rclone"]')
CADA_DUCKDNS = 600     # segundos entre avisos a DuckDNS
CADA_VUELTA = 15       # segundos entre comprobaciones del SFTP y de la configuración
ESPERA_REINTENTO = 30  # si rclone se cae, se vuelve a lanzar tras esto

CAMPOS = {  # nombre: (obligatorio para el SFTP, es secreto, valor por defecto)
    "ftp_host": (True, False, "192.168.1.1"),
    "ftp_usuario": (True, False, ""),
    "ftp_clave": (True, True, ""),
    "ftp_carpeta": (False, False, "/usb1_1_1"),
    "sftp_puerto": (False, False, 2222),
    "srv_puerto": (False, False, 2223),   # entrada de los servidores (solo clave, raíz en servidores/)
    "sftp_usuario": (True, False, ""),
    "sftp_clave": (True, True, ""),
    "duckdns_dominio": (False, False, ""),
    "duckdns_token": (False, True, ""),
}


def ruta_config() -> str:
    return estado.ruta("nas.json")


def ruta_estado() -> str:
    return estado.ruta("nas_estado.json")


def ruta_claves() -> str:
    """Claves públicas SSH autorizadas en la entrada principal (la que ve todo el disco)."""
    return estado.ruta("nas_authorized_keys")


def ruta_claves_srv() -> str:
    """Claves públicas de los servidores que mandan copias: solo entran por la entrada de servidores."""
    return estado.ruta("nas_srv_authorized_keys")


def carpeta_srv(cfg: dict) -> str:
    return str(valor(cfg, "ftp_carpeta")).rstrip("/") + "/servidores"


def leer_config() -> dict:
    try:
        with open(ruta_config(), encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir_privado(destino: str, texto: str) -> None:
    carpeta = os.path.dirname(destino)
    fd, temporal = tempfile.mkstemp(prefix=".nas-", dir=carpeta)
    try:
        os.chmod(temporal, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(temporal, destino)
    except OSError:
        try:
            os.remove(temporal)
        except OSError:
            pass
        raise


def guardar_config(cambios: dict) -> dict:
    """Mezcla los cambios con lo guardado. Solo campos conocidos; un secreto vacío no borra el guardado."""
    if not isinstance(cambios, dict):
        raise ValueError("Se esperaba un objeto")
    cfg = leer_config()
    for clave, valor in cambios.items():
        if clave not in CAMPOS:
            raise ValueError(f"Campo desconocido: {clave}")
        if clave in ("sftp_puerto", "srv_puerto"):
            try:
                valor = int(valor)
            except (TypeError, ValueError):
                raise ValueError(f"{clave} tiene que ser un número") from None
            if not 1024 <= valor <= 65535:
                raise ValueError(f"{clave} tiene que estar entre 1024 y 65535")
        else:
            valor = str(valor).strip()
            if any(c.isspace() for c in valor):
                raise ValueError(f"{clave} no puede llevar espacios")
            if CAMPOS[clave][1] and not valor:
                continue
        cfg[clave] = valor
    # (aquí «valor» es la variable del bucle, no la función: se leen los puertos a mano)
    if int(cfg.get("srv_puerto", CAMPOS["srv_puerto"][2])) == int(cfg.get("sftp_puerto", CAMPOS["sftp_puerto"][2])):
        raise ValueError("srv_puerto y sftp_puerto no pueden ser el mismo")
    _escribir_privado(ruta_config(), json.dumps(cfg, ensure_ascii=False))
    return cfg


def anadir_clave_publica(linea: str, destino: str = "nas") -> int:
    """Añade una clave pública SSH (ssh-ed25519/ssh-rsa/ecdsa-...) si no estaba. Devuelve cuántas hay.
    destino «nas» = entrada principal; «servidores» = entrada de las copias de los servidores."""
    rutas = {"nas": ruta_claves(), "servidores": ruta_claves_srv()}
    if destino not in rutas:
        raise ValueError("destino tiene que ser «nas» o «servidores»")
    linea = " ".join(str(linea).split())
    partes = linea.split(" ")
    if len(partes) < 2 or not partes[0].startswith(("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-")) or len(partes[1]) < 40:
        raise ValueError("No parece una clave pública SSH")
    try:
        with open(rutas[destino], encoding="utf-8") as f:
            actuales = [l.strip() for l in f if l.strip()]
    except OSError:
        actuales = []
    if not any(a.split(" ")[1:2] == partes[1:2] for a in actuales):
        actuales.append(linea)
    _escribir_privado(rutas[destino], "\n".join(actuales) + "\n")
    return len(actuales)


def valor(cfg: dict, clave: str):
    return cfg.get(clave, CAMPOS[clave][2])


def sftp_configurado(cfg: dict) -> bool:
    return all(valor(cfg, c) for c, (oblig, _, _) in CAMPOS.items() if oblig)


def ofuscar(clave: str) -> str:
    """rclone pide las claves de los remotos «ofuscadas» (rclone obscure); la clave entra por stdin, no en la orden."""
    r = subprocess.run(RCLONE + ["obscure", "-"], input=clave + "\n", capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"rclone obscure ha fallado: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def orden_y_entorno(cfg: dict, clave_ofuscada: str):
    """La orden de rclone y su entorno. El remoto FTP se define al vuelo (:ftp:) con variables de entorno."""
    orden = RCLONE + ["serve", "sftp", ":ftp:" + valor(cfg, "ftp_carpeta"),
             "--addr", f":{int(valor(cfg, 'sftp_puerto'))}",
             "--user", valor(cfg, "sftp_usuario"), "--pass", valor(cfg, "sftp_clave"),
             "--vfs-cache-mode", "off", "--log-level", "NOTICE"]
    if os.path.exists(ruta_claves()):
        orden += ["--authorized-keys", ruta_claves()]
    return orden, _entorno_ftp(cfg, clave_ofuscada)


def orden_y_entorno_srv(cfg: dict, clave_ofuscada: str):
    """Entrada de los servidores: raíz en servidores/, SIN usuario ni contraseña (solo sus claves SSH)."""
    orden = RCLONE + ["serve", "sftp", ":ftp:" + carpeta_srv(cfg),
             "--addr", f":{int(valor(cfg, 'srv_puerto'))}",
             "--authorized-keys", ruta_claves_srv(),
             "--vfs-cache-mode", "off", "--log-level", "NOTICE"]
    return orden, _entorno_ftp(cfg, clave_ofuscada)


def _entorno_ftp(cfg: dict, clave_ofuscada: str) -> dict:
    entorno = dict(os.environ)
    entorno.update({
        "RCLONE_FTP_HOST": valor(cfg, "ftp_host"),
        "RCLONE_FTP_USER": valor(cfg, "ftp_usuario"),
        "RCLONE_FTP_PASS": clave_ofuscada,
        "RCLONE_FTP_CONCURRENCY": "4",  # el FTP del router no quiere muchas conexiones a la vez
    })
    return entorno


def avisar_duckdns(cfg: dict) -> dict:
    """Pide a DuckDNS que apunte el nombre a la IP desde la que llega la petición (la de casa)."""
    consulta = urllib.parse.urlencode({"domains": valor(cfg, "duckdns_dominio"),
                                       "token": valor(cfg, "duckdns_token"), "ip": "", "verbose": "true"})
    try:
        with urllib.request.urlopen(f"{DUCKDNS_URL}?{consulta}", timeout=20) as r:
            lineas = r.read().decode("utf-8", "replace").splitlines()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detalle": f"sin respuesta: {e.__class__.__name__}"}
    if not lineas or lineas[0].strip() != "OK":
        return {"ok": False, "detalle": "DuckDNS dice KO (nombre o token mal)"}
    return {"ok": True, "ip": lineas[1].strip() if len(lineas) > 1 else "",
            "detalle": lineas[3].strip() if len(lineas) > 3 else ""}


def leer_estado_publico() -> dict:
    try:
        with open(ruta_estado(), encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def estado_publico() -> dict:
    """Lo que enseña GET /api/nas: nada de claves."""
    cfg = leer_config()
    vivo = leer_estado_publico()
    return {
        "configurado": sftp_configurado(cfg),
        "sftp_puerto": valor(cfg, "sftp_puerto"),
        "sftp_usuario": valor(cfg, "sftp_usuario"),
        "ftp_host": valor(cfg, "ftp_host"),
        "ftp_carpeta": valor(cfg, "ftp_carpeta"),
        "duckdns_dominio": valor(cfg, "duckdns_dominio"),
        "claves_autorizadas": _contar_claves(),
        "servidores": {"puerto": valor(cfg, "srv_puerto"), "carpeta": carpeta_srv(cfg),
                       "claves_autorizadas": _contar_claves(ruta_claves_srv())},
        "pasarela": vivo,
        "latido_reciente": time.time() - float(vivo.get("hora", 0) or 0) < 120,
    }


def _contar_claves(ruta: str = "") -> int:
    try:
        with open(ruta or ruta_claves(), encoding="utf-8") as f:
            return sum(1 for l in f if l.strip())
    except OSError:
        return 0


class Pasarela:
    """Mantiene rclone en marcha y el nombre de DuckDNS al día. Una vuelta = paso()."""

    def __init__(self):
        self.proceso = None
        self.firma = None          # configuración con la que se lanzó rclone
        self.proximo_lanzamiento = 0.0
        self.proximo_duckdns = 0.0
        self.ultimo_duckdns = {}
        self.ultimo_error = ""
        self.arranques = 0
        # entrada de los servidores (otro rclone, otro puerto, solo claves, raíz en servidores/)
        self.srv_proceso = None
        self.srv_firma = None
        self.srv_proximo = 0.0
        self.srv_error = ""
        self.srv_arranques = 0

    @staticmethod
    def _terminar(proceso):
        if proceso and proceso.poll() is None:
            proceso.terminate()
            try:
                proceso.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proceso.kill()

    def _parar(self):
        self._terminar(self.proceso)
        self.proceso = None

    def _parar_srv(self):
        self._terminar(self.srv_proceso)
        self.srv_proceso = None

    @staticmethod
    def _abrir_log(nombre: str):
        ruta_log = estado.ruta(nombre)
        if os.path.exists(ruta_log) and os.path.getsize(ruta_log) > 2_000_000:  # que no crezca sin fin
            os.replace(ruta_log, ruta_log + ".1")
        return open(ruta_log, "ab")

    def _lanzar_srv(self, cfg):
        if shutil.which(RCLONE[0]) is None and not os.path.exists(RCLONE[0]):
            self.srv_error = "rclone no está instalado (pkg install rclone)"
            return
        try:
            orden, entorno = orden_y_entorno_srv(cfg, ofuscar(valor(cfg, "ftp_clave")))
            # que exista la carpeta servidores/ (si ya existe, rclone mkdir no hace nada)
            subprocess.run(RCLONE + ["mkdir", ":ftp:" + carpeta_srv(cfg)], env=entorno, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=60)
            registro = self._abrir_log("nas_rclone_servidores.log")
            self.srv_proceso = subprocess.Popen(orden, env=entorno, stdin=subprocess.DEVNULL,
                                                stdout=registro, stderr=subprocess.STDOUT)
            registro.close()
            self.srv_arranques += 1
            self.srv_error = ""
        except Exception as e:  # noqa: BLE001
            self.srv_proceso = None
            self.srv_error = f"no arranca rclone de servidores: {e}"

    def _lanzar(self, cfg):
        if shutil.which(RCLONE[0]) is None and not os.path.exists(RCLONE[0]):
            self.ultimo_error = "rclone no está instalado (pkg install rclone)"
            return
        try:
            orden, entorno = orden_y_entorno(cfg, ofuscar(valor(cfg, "ftp_clave")))
            registro = self._abrir_log("nas_rclone.log")
            self.proceso = subprocess.Popen(orden, env=entorno, stdin=subprocess.DEVNULL,
                                            stdout=registro, stderr=subprocess.STDOUT)
            registro.close()
            self.arranques += 1
            self.ultimo_error = ""
        except Exception as e:  # noqa: BLE001
            self.proceso = None
            self.ultimo_error = f"no arranca rclone: {e}"

    def paso(self, ahora=None):
        ahora = time.time() if ahora is None else ahora
        cfg = leer_config()
        base = json.dumps({k: valor(cfg, k) for k in CAMPOS if not k.startswith("duckdns")}, sort_keys=True)
        firma = base + (str(os.path.getmtime(ruta_claves())) if os.path.exists(ruta_claves()) else "")
        if not sftp_configurado(cfg):
            self._parar()
        else:
            if firma != self.firma:      # configuración nueva: se relanza con ella
                self._parar()
                self.firma = firma
                self.proximo_lanzamiento = 0.0
            if self.proceso is not None and self.proceso.poll() is not None:
                self.ultimo_error = f"rclone se ha parado (código {self.proceso.returncode})"
                self.proceso = None
                self.proximo_lanzamiento = ahora + ESPERA_REINTENTO
            if self.proceso is None and ahora >= self.proximo_lanzamiento:
                self._lanzar(cfg)
                if self.proceso is None:
                    self.proximo_lanzamiento = ahora + ESPERA_REINTENTO
        # entrada de los servidores: solo si hay al menos una clave suya (sin claves no hay forma de entrar)
        srv_firma = base + (str(os.path.getmtime(ruta_claves_srv())) if os.path.exists(ruta_claves_srv()) else "")
        if not sftp_configurado(cfg) or _contar_claves(ruta_claves_srv()) == 0:
            self._parar_srv()
            self.srv_firma = None
        else:
            if srv_firma != self.srv_firma:
                self._parar_srv()
                self.srv_firma = srv_firma
                self.srv_proximo = 0.0
            if self.srv_proceso is not None and self.srv_proceso.poll() is not None:
                self.srv_error = f"rclone de servidores se ha parado (código {self.srv_proceso.returncode})"
                self.srv_proceso = None
                self.srv_proximo = ahora + ESPERA_REINTENTO
            if self.srv_proceso is None and ahora >= self.srv_proximo:
                self._lanzar_srv(cfg)
                if self.srv_proceso is None:
                    self.srv_proximo = ahora + ESPERA_REINTENTO
        if valor(cfg, "duckdns_dominio") and valor(cfg, "duckdns_token"):
            if ahora >= self.proximo_duckdns:
                self.ultimo_duckdns = dict(avisar_duckdns(cfg), hora=ahora)
                self.proximo_duckdns = ahora + (CADA_DUCKDNS if self.ultimo_duckdns["ok"] else 120)
        else:
            self.ultimo_duckdns = {}
        vivo = {
            "hora": ahora,
            "sftp_activo": self.proceso is not None and self.proceso.poll() is None,
            "arranques": self.arranques,
            "error": self.ultimo_error,
            "servidores_activo": self.srv_proceso is not None and self.srv_proceso.poll() is None,
            "servidores_error": self.srv_error,
            "duckdns": self.ultimo_duckdns,
        }
        _escribir_privado(ruta_estado(), json.dumps(vivo, ensure_ascii=False))
        return vivo

    def cerrar(self):
        self._parar()
        self._parar_srv()


def main():
    pasarela = Pasarela()
    print("[NAS] Pasarela en marcha", flush=True)
    anterior = None
    try:
        while not os.path.exists(os.path.join(os.path.dirname(estado.ruta("x")), "..", "parar")):
            vivo = pasarela.paso()
            resumen = (vivo["sftp_activo"], vivo["error"], vivo["servidores_activo"], vivo["servidores_error"],
                       vivo["duckdns"].get("ok"), vivo["duckdns"].get("ip"))
            if resumen != anterior:
                print(f"[NAS] {time.strftime('%F %T')} SFTP {'activo' if vivo['sftp_activo'] else 'parado'}"
                      f"{' — ' + vivo['error'] if vivo['error'] else ''}; servidores "
                      f"{'activo' if vivo['servidores_activo'] else 'parado'}"
                      f"{' — ' + vivo['servidores_error'] if vivo['servidores_error'] else ''}; "
                      f"DuckDNS {vivo['duckdns'] or 'sin configurar'}", flush=True)
                anterior = resumen
            time.sleep(CADA_VUELTA)
    finally:
        pasarela.cerrar()


if __name__ == "__main__":
    main()
