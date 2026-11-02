"""
La casa: Home Assistant (luces, llamada en el móvil, timbre con cámara) y el ambilight (HyperHDR).

PREPARADO: no hace nada mientras no se ponga la dirección y el token de Home Assistant (o la de HyperHDR) en
«⚙️ Ajustes» del mando. Habla con la API REST de Home Assistant con un token de larga duración
(Perfil → Seguridad → Tokens de acceso de larga duración); con HyperHDR, por su API JSON.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

import ajustes

ESCENA = "tvhub_antes_del_cine"   # foto de las luces antes de bajarlas, para dejarlas como estaban


class Casa:
    def __init__(self, leer_ajustes=ajustes.leer):
        self.leer = leer_ajustes

    # ------------------------------------------------------------ Home Assistant
    def configurada(self) -> bool:
        a = self.leer()
        return bool(a.get("ha_url") and a.get("ha_token"))

    def _peticion(self, metodo, ruta, datos=None, crudo=False, timeout=5):
        a = self.leer()
        if not (a.get("ha_url") and a.get("ha_token")):
            return None
        cuerpo = json.dumps(datos).encode("utf-8") if datos is not None else None
        peticion = urllib.request.Request(a["ha_url"] + ruta, data=cuerpo, method=metodo,
                                          headers={"Authorization": "Bearer " + a["ha_token"],
                                                   "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=timeout) as r:
                contenido = r.read()
                return contenido if crudo else json.loads(contenido.decode("utf-8") or "null")
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def probar(self):
        """(correcto, mensaje) para el botón «Probar» de los ajustes."""
        if not self.configurada():
            return False, "Falta la dirección o el token de Home Assistant"
        r = self._peticion("GET", "/api/")
        if isinstance(r, dict) and r.get("message"):
            return True, "Home Assistant responde"
        return False, "Home Assistant no responde (mira la dirección y el token)"

    def estado(self, entidad):
        if not entidad:
            return None
        r = self._peticion("GET", "/api/states/" + urllib.parse.quote(entidad))
        return r.get("state") if isinstance(r, dict) else None

    def servicio(self, dominio, servicio, datos=None) -> bool:
        return self._peticion("POST", f"/api/services/{dominio}/{servicio}", datos or {}) is not None

    def luces(self) -> list:
        return [e for e in (self.leer().get("ha_luces") or "").split(",") if e]

    def luces_cine(self) -> bool:
        """Foto de cómo están las luces y las baja al brillo de cine."""
        luces = self.luces()
        if not luces:
            return False
        self.servicio("scene", "create", {"scene_id": ESCENA, "snapshot_entities": luces})
        return self.servicio("light", "turn_on", {"entity_id": luces,
                                                  "brightness_pct": int(self.leer().get("ha_brillo_cine") or 15)})

    def luces_como_antes(self) -> bool:
        if not self.luces():
            return False
        return self.servicio("scene", "turn_on", {"entity_id": "scene." + ESCENA})

    def luces_encender(self, encender=True) -> bool:
        luces = self.luces()
        return bool(luces) and self.servicio("light", "turn_on" if encender else "turn_off", {"entity_id": luces})

    def foto(self, camara=None):
        """JPEG de la cámara (bytes) o None."""
        camara = camara or self.leer().get("ha_camara")
        if not camara:
            return None
        datos = self._peticion("GET", "/api/camera_proxy/" + urllib.parse.quote(camara), crudo=True, timeout=8)
        return datos if datos and datos[:2] == b"\xff\xd8" else None

    # ------------------------------------------------------------ Ambilight (HyperHDR)
    def ambilight(self, encender: bool) -> bool:
        url = (self.leer().get("hyperhdr_url") or "").rstrip("/")
        if not url:
            return False
        orden = {"command": "componentstate", "componentstate": {"component": "ALL", "state": bool(encender)}}
        peticion = urllib.request.Request(url + "/json-rpc", data=json.dumps(orden).encode("utf-8"), method="POST",
                                          headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=4) as r:
                return bool(json.loads(r.read().decode("utf-8") or "{}").get("success"))
        except (urllib.error.URLError, OSError, ValueError):
            return False


def es_cine(programa) -> bool:
    """¿Es una película? Por la categoría de la guía («Cine», «Película»...)."""
    texto = " ".join(str((programa or {}).get(k) or "") for k in ("categoria", "titulo")).lower()
    return bool(re.search(r"\bcine\b|pel[ií]cula", texto))
