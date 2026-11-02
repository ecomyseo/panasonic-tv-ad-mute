"""
Vuelta al canal: durante los anuncios se puede zapear libremente y la TV vuelve sola al canal
donde empezaron.

La TV tiene un solo sintonizador: mientras estás en otro canal no puede ver si los anuncios del
primero han terminado. Por eso:
  1. la hora de volver se ESTIMA con lo que duraron los cortes de ese canal otras veces
     (se aprende solo: mediana de los últimos cortes medidos enteros);
  2. al volver se COMPRUEBA: si los anuncios siguen, el silenciador los calla hasta que acaben,
     y esa duración real corrige la estimación siguiente.

Esta clase solo decide; quien la usa (el silenciador) cambia de canal y quita o devuelve el sonido.
Los números de canal se aprenden del rótulo que la TV enseña al cambiar (MtkTvBannerBase).
"""

import json
import os
import statistics
import threading
import time

import estado

INACTIVA = "inactiva"
EN_PUBLI = "en_publi"        # anuncios en el canal que se está viendo
FUERA = "fuera"              # el usuario se ha ido a otro canal; hay que volver
COMPROBANDO = "comprobando"  # acabamos de volver: si siguen los anuncios, se silencian

MUESTRAS = 7  # cortes que se recuerdan por canal


def codigos_numero(numero):
    """'14' -> [8, 11] (KEYCODE_1, KEYCODE_4)."""
    texto = str(numero).strip()
    if not texto.isdigit():
        return []
    return [7 + int(c) for c in texto]


class Vuelta:
    def __init__(self, duracion_defecto=300, antelacion=15, ventana_comprobacion=45,
                 espera_minima=30, maximo_fuera=1200, ruta=None, reloj=time.time):
        self.duracion_defecto = max(30, int(duracion_defecto))
        self.antelacion = max(0, int(antelacion))
        self.ventana = max(10, int(ventana_comprobacion))
        self.espera_minima = max(5, int(espera_minima))
        self.maximo_fuera = max(60, int(maximo_fuera))
        self.ruta = ruta or estado.ruta("vuelta.json")
        self.reloj = reloj
        self._lock = threading.RLock()
        self.estado = INACTIVA
        self.origen = None
        self.inicio = 0.0
        self.hora_vuelta = 0.0
        self.comprobar_hasta = 0.0
        self.saltos = 0
        self.datos = self._cargar()

    # ----------------------------------------------------------- aprendizaje
    def _cargar(self):
        try:
            with open(self.ruta, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                d.setdefault("numeros", {})
                d.setdefault("duraciones", {})
                return d
        except (OSError, ValueError):
            pass
        return {"numeros": {}, "duraciones": {}}

    def _guardar(self):
        tmp = self.ruta + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.datos, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.ruta)
        except OSError:
            pass

    def anotar_numero(self, nombre, numero):
        nombre = (nombre or "").strip()
        numero = str(numero or "").strip()
        if not nombre or not numero.isdigit():
            return
        with self._lock:
            if self.datos["numeros"].get(nombre) != numero:
                self.datos["numeros"][nombre] = numero
                self._guardar()

    def numero(self, nombre):
        return self.datos["numeros"].get(nombre or "")

    def anotar_duracion(self, nombre, segundos):
        if not nombre or segundos < 20 or segundos > 1800:
            return  # un «corte» de menos de 20 s o de más de media hora no es una medida fiable
        with self._lock:
            lista = self.datos["duraciones"].setdefault(nombre, [])
            lista.append(int(segundos))
            del lista[:-MUESTRAS]
            self._guardar()

    def duracion_estimada(self, nombre):
        lista = self.datos["duraciones"].get(nombre or "") or []
        if not lista:
            return self.duracion_defecto
        return int(statistics.median(lista))

    # --------------------------------------------------------------- eventos
    def publi_empieza(self, canal):
        """Ha empezado (o sigue) la publicidad en el canal que se está viendo."""
        ahora = self.reloj()
        with self._lock:
            if self.estado == COMPROBANDO and canal == self.origen:
                # Hemos vuelto antes de tiempo: se sigue midiendo desde el principio del corte
                self.estado = EN_PUBLI
                return
            if self.estado == EN_PUBLI and canal == self.origen:
                return
            self.estado = EN_PUBLI
            self.origen = canal
            self.inicio = ahora
            self.saltos = 0

    def publi_termina(self, canal):
        """Fin de la publicidad visto en el canal actual. Devuelve los segundos medidos (o 0)."""
        ahora = self.reloj()
        with self._lock:
            if self.estado != EN_PUBLI or canal != self.origen:
                return 0
            dur = ahora - self.inicio
            self.anotar_duracion(canal, dur)
            self._reiniciar()
            return int(dur)

    def cambio_canal(self, canal, propio=False):
        """
        Cambio de canal. Devuelve 'restaurar' si hay que devolver el sonido (el usuario se ha ido
        a otro canal en mitad de los anuncios), o None.
        """
        ahora = self.reloj()
        with self._lock:
            if propio:
                return None
            if self.estado == EN_PUBLI and canal != self.origen:
                self.estado = FUERA
                self.saltos = 1
                vuelta = self.inicio + self.duracion_estimada(self.origen) - self.antelacion
                self.hora_vuelta = max(vuelta, ahora + self.espera_minima)
                return "restaurar"
            if self.estado == FUERA:
                if canal == self.origen:
                    # Ha vuelto él solo: se comprueba si siguen los anuncios
                    self.estado = COMPROBANDO
                    self.comprobar_hasta = ahora + self.ventana
                else:
                    self.saltos += 1
                return None
            if self.estado == COMPROBANDO and canal != self.origen:
                self._reiniciar()  # se ha ido otra vez sin que hubiera anuncios: decide él
            return None

    def tick(self):
        """Se llama cada segundo. Devuelve 'volver' cuando toca volver al canal de origen."""
        ahora = self.reloj()
        with self._lock:
            if self.estado == FUERA:
                if ahora - self.inicio > self.maximo_fuera:
                    self._reiniciar()
                    return None
                if ahora >= self.hora_vuelta:
                    self.estado = COMPROBANDO
                    self.comprobar_hasta = ahora + self.ventana
                    return "volver"
            elif self.estado == COMPROBANDO and ahora > self.comprobar_hasta:
                self._reiniciar()
            elif self.estado == EN_PUBLI and ahora > self.inicio + self.duracion_estimada(self.origen) + self.ventana:
                # No se ha visto el final: se da el corte por acabado (sin aprender nada de él), para que
                # un zapeo normal de después no provoque una vuelta que nadie quiere.
                self._reiniciar()
            return None

    def volver_ya(self):
        with self._lock:
            if self.estado == FUERA:
                self.hora_vuelta = self.reloj()
                return True
            return False

    def cancelar(self):
        with self._lock:
            hubo = self.estado in (FUERA, COMPROBANDO)
            self._reiniciar()
            return hubo

    def _reiniciar(self):
        self.estado = INACTIVA
        self.origen = None
        self.inicio = 0.0
        self.hora_vuelta = 0.0
        self.comprobar_hasta = 0.0
        self.saltos = 0

    def resumen(self):
        with self._lock:
            r = {"estado": self.estado, "origen": self.origen}
            if self.estado == FUERA:
                r["hora_vuelta"] = self.hora_vuelta
                r["numero"] = self.numero(self.origen)
            if self.estado in (EN_PUBLI, FUERA, COMPROBANDO) and self.origen:
                r["estimada"] = self.duracion_estimada(self.origen)
                r["desde"] = self.inicio
            return r
