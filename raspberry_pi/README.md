# Instalación en Raspberry Pi Zero 2 W

Qué queda funcionando en la Raspberry, día y noche:

* **Silenciador de publicidad** (servicio `panasonic-mute`): quita el sonido con el botón del móvil o al ver
  en la TV el marcador del corte (`AD_PATTERNS`, vacío hasta tener uno confirmado) y lo devuelve a los
  `MUTE_DURATION` segundos. Si devuelves el sonido con el mando antes de tiempo, no lo vuelve a quitar.
* **Mando web para el móvil** (servicio `panasonic-web`, puerto 8080): silenciar / devolver el sonido,
  pausar el silenciador, lo que se emite ahora con su ficha, mando a distancia, canales, apps instaladas,
  escribir en la TV, temporizador de apagado, DNS antirrastreo y salud de la Raspberry.
* **Vuelta al canal**: si cambias de canal durante los anuncios (después de pulsar «Silenciar anuncios» o de
  que salte el marcador), la TV vuelve sola al canal donde empezaron cuando calcula que han acabado.
* **Recordatorios con la guía**: eliges un programa en el móvil y, cuando empieza, la TV pone su canal o te
  llega un WhatsApp (o las dos cosas).
* **Avisos en la pantalla** («Vuelvo a Antena 3 en 30 s»), en el centro y con letra grande, con la app propia
  «TV Hub Avisos»: en el móvil, «Preparar avisos» la instala.
* **Guía de programación** de la TDT descargada cada 4 horas (unos 30 s de CPU en la Zero 2 W).
* **Apagado nocturno** opcional a una hora fija, bajando el volumen poco a poco.
* **Encendido por la red** (Wake-on-LAN) si pones la MAC de la TV en la configuración.
* Orden **`tvhub`** para todo lo demás (menú, estado, registro, configuración, emparejar la TV).

---

## 1. Grabar la tarjeta MicroSD (5 minutos)

1. Instala **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)** en el ordenador.
2. **Dispositivo:** `Raspberry Pi Zero 2 W`. **Sistema:** `Raspberry Pi OS (other)` → **`Raspberry Pi OS Lite (64-bit)`**.
3. Pulsa **SIGUIENTE** → **EDITAR AJUSTES**:
   * **Nombre del equipo:** `raspberrypi` (o el que quieras; luego se usa como `nombre.local`).
   * **Usuario y contraseña:** por ejemplo `pi` y una contraseña tuya.
   * **Wi-Fi:** el nombre y la contraseña de casa. País: `ES`.
   * Pestaña **Servicios:** marca **Habilitar SSH** con contraseña.
4. **GUARDAR** → **SÍ** para grabar.

## 2. Montar y encender

1. Disipador en el chip, la Pi en su caja y la MicroSD en la ranura.
2. Alimentación por el micro-USB **`PWR IN`**. Mejor con el cargador del kit: el USB de muchas TV no da
   corriente suficiente y la Pi se cuelga (el mando web lo avisa en «Alimentación»).
3. Espera un par de minutos a que arranque y se conecte al Wi-Fi.

## 3. Preparar la TV (una sola vez)

1. **Ajustes → Sistema → Información** → pulsa 7 veces **«Compilación del SO de Android TV»**.
2. **Ajustes → Sistema → Opciones para desarrolladores** → activa **Depuración USB** (y la de red si aparece).
3. Fija la IP de la TV en el router (DHCP estático) para que no cambie.

## 4. Instalar (desde el ordenador con Windows)

Doble clic en **`INSTALAR_EN_RASPBERRY.bat`** (en la raíz del proyecto). Te pregunta el nombre de la Raspberry
(`raspberrypi.local`), el usuario y la IP de la TV, envía el programa por SSH y lo instala.

* Pide la contraseña de la Raspberry **dos veces** (envío e instalación). Si tienes clave SSH
  (`%USERPROFILE%\.ssh\id_ed25519.pub`), la deja autorizada y las siguientes veces ya no la pide.
* Durante la instalación **mira la TV**: aparece «¿Permitir la depuración?». Marca **«Permitir siempre»** y
  acepta. Si no estabas delante, luego basta con `tvhub parear`.
* Para **actualizar**, se vuelve a ejecutar el mismo `.bat`: la configuración se conserva.

Sin Windows, desde la propia Raspberry:

```bash
git clone https://github.com/ecomyseo/panasonic-tv-ad-mute.git
cd panasonic-tv-ad-mute
sudo bash raspberry_pi/install.sh --tv-ip 192.168.1.132
```

## 5. Usarlo

* **Móvil:** abre `http://raspberrypi.local:8080` (o la IP que muestra el instalador) y añádelo a la
  pantalla de inicio.
* **Consola** (`ssh pi@raspberrypi.local`):

| Orden | Qué hace |
|---|---|
| `tvhub` | Menú interactivo |
| `tvhub estado` | Estado de los servicios y de la conexión con la TV |
| `tvhub logs` | Registro en directo |
| `tvhub parear` | Conectar con la TV y esperar a que aceptes el aviso |
| `tvhub config` | Editar la configuración y reiniciar |
| `tvhub epg` | Descargar la guía ahora |
| `tvhub aprendizaje` | Ver lo que la TV registra (con `MODO_APRENDIZAJE=1`) |
| `tvhub diagnostico` | Puertos de control que tiene abiertos la TV |
| `tvhub desinstalar` | Quitarlo todo (conserva la configuración) |

## 6. Configuración

Fichero `/etc/panasonic-tv-hub/config.env` (`tvhub config`). Lo más habitual:

| Opción | Para qué |
|---|---|
| `TV_IP` | IP de la TV (`:5555` se añade solo) |
| `TV_MAC` | MAC de la TV para encenderla por la red |
| `MUTE_DURATION` | Segundos de silencio por corte (150) |
| `AD_PATTERNS` | Textos del logcat que marcan el inicio de los anuncios |
| `AD_END_PATTERNS` | Textos del logcat que marcan el final de los anuncios |
| `VOLVER_AL_CANAL` | `1` = si cambias de canal en los anuncios, la TV vuelve sola al acabar |
| `DURACION_PUBLI` | Segundos que se calcula que dura un corte hasta tener medidas de ese canal (300) |
| `WEB_NOMBRES_PERMITIDOS` | El mando solo responde a la red de casa; aquí, nombres con puntos de más para abrirlo (p. ej. `tele.midominio.es`) |
| `AVISOS_EN_TV` | `1` = avisos en la pantalla (app «TV Hub Avisos»); `0` = sin avisos |
| `AVISOS_DURACION` | Segundos que se ve cada aviso (8) |
| `AVISOS_TAMANO` | Tamaño de la letra del título del aviso, de 18 a 96 (40) |
| `AVISOS_POSICION` | `centro`, `arriba` o `abajo` (`centro`) |
| `TVOVERLAY_URL` | Solo si se usa TvOverlay en lugar de la app propia (vacío = la IP de la TV, puerto 5001) |
| `FICHA_AL_CAMBIAR` | `1` = al cambiar de canal, la ficha de lo que echan, una vez por programa (1) |
| `FICHA_ESPERA` / `FICHA_SEGUNDOS` | Segundos en el canal antes de enseñarla (3) y que se ve (10) |
| `GUIA_SILENCIA` | `1` = silenciar con la señal de la guía; `0` = solo apuntarla junto a tus pulsaciones (0) |
| `GUIA_TRAS_ZAPEO` / `GUIA_CALMA` | Segundos tras zapear en que no cuenta (20) y de calma para un corte nuevo (480) |
| `RECORDATORIO_ANTELACION` | Segundos antes de empezar el programa en que salta un recordatorio (60) |
| `MODO_APRENDIZAJE` | `1` = guarda el logcat de la TV para afinar `AD_PATTERNS` |
| `APAGADO_NOCTURNO` | `01:30` = apaga la TV a esa hora si sigue encendida |
| `TMDB_API_KEY` | Clave gratuita de TMDb para notas y carátulas de cine |

### Afinar la detección de anuncios

De fábrica `AD_PATTERNS` va vacío: los marcadores que se usaban antes (`exchangeType==28`,
`getHBBTVBannerControl`) la TV los escribe cada 30 segundos haya anuncios o no, y se ignoran aunque estén en la
configuración. Hasta tener uno confirmado, se silencia con el botón del móvil (y la vuelta al canal funciona igual).
Para buscar el marcador de tu TV:

1. `tvhub config` → `MODO_APRENDIZAJE=1`.
2. `tvhub aprendizaje` y mira qué línea aparece justo cuando empieza la publicidad.
3. Añade ese texto a `AD_PATTERNS` (separado por comas) y vuelve a `MODO_APRENDIZAJE=0`.

### WhatsApp (opcional y privado)

Si `mensajero_whatsapp_privado/credenciales_privadas.json` tiene tu clave y tu teléfono, el instalador
de Windows lo lleva a la Raspberry y aparece el botón **«A mi WhatsApp»**, que manda la ficha de lo que se
emite. No se sube nunca al repositorio.

## Dónde está cada cosa en la Raspberry

```text
/opt/panasonic-tv-hub/          programa (se sustituye al actualizar)
/etc/panasonic-tv-hub/config.env  configuración (se conserva)
/var/lib/panasonic-tv-hub/      estado, guía EPG, estadísticas y aprendizaje.log
/usr/local/bin/tvhub            orden de control
```
