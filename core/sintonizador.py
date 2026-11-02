"""
Segundo sintonizador de TDT por USB en la Raspberry. PREPARADO, sin montar: hasta que se conecte uno, solo dice si
lo hay.

Para qué servirá: ver en el móvil el canal donde empezaron los anuncios mientras se zapea en la tele, y saber de
verdad cuándo acaban mirando ese canal (por ejemplo, el logotipo de la cadena, que suele desaparecer en los cortes).

Cuál comprar: uno que Linux reconozca solo. Los de chip RTL2832U + R820T2 reciben DVB-T, que es como se emiten hoy
los canales HD de la TDT española (DVB-T2 solo lo usan los UHD). La Zero 2 W tiene un solo USB de datos: hace falta
un adaptador OTG micro-USB a USB-A. La señal se saca de la antena con un repartidor de 2 salidas.

Cuando esté: `dvbv5-scan` para sacar los canales y `dvbv5-zap` + ffmpeg (sin recodificar) para mandarlo al móvil.
"""

import glob
import os


def detectados() -> list:
    """Adaptadores DVB que ve el sistema (/dev/dvb/adapterN). En Windows, ninguno."""
    if os.name == "nt":
        return []
    return sorted(os.path.basename(p) for p in glob.glob("/dev/dvb/adapter*"))
