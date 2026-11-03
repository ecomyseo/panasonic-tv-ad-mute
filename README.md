# 📺 Panasonic Google TV Smart Hub & Ad-Mute Suite

Sistema integral de automatización, privacidad, mando a distancia inteligente y silenciador automático de publicidad para televisores **Panasonic con Google TV / Android 14** (y Viera).

Diseñado específicamente para ejecutarse de forma autónoma en una **Raspberry Pi Zero 2 W** (24/7 de bajo consumo), en tu ordenador con **Windows**, o mediante un microcontrolador **ESP32**.

---

## 🌟 Características y Módulos Incluidos

### 1. 🔇 Silenciador Automático de Publicidad
* Escucha el registro de la TV por ADB y silencia al ver el texto que marca el corte (`AD_PATTERNS`); devuelve el
  sonido a los `MUTE_DURATION` segundos (150 por defecto). También se silencia con el botón del móvil.
* **Aviso (medido el 2/11/2026):** los marcadores que traía (`exchangeType==28`, `getHBBTVBannerControl`) la TV los
  escribe **cada 30 segundos, haya anuncios o no**; se ignoran. Todavía no hay un marcador confirmado en esta TV, así
  que de fábrica `AD_PATTERNS` va vacío y se silencia con el botón.
* Comprueba el estado real del sonido: si ya estaba silenciada no la toca, y si devuelves el sonido con el mando antes de tiempo no lo vuelve a quitar.
* Se puede pausar desde el móvil, cuenta los cortes silenciados del día y tiene un modo aprendizaje para afinar los marcadores en cada TV.
* **Señal de la guía (candidata, sin confirmar):** con Antena 3 puesta, la cadena reenvió el «ahora» del canal (mismo
  programa, otro identificador) siete veces en 9 minutos y ninguna en la media hora anterior: puede ser el corte. El hub
  la escucha y la **apunta junto a tus pulsaciones de «Silenciar»**; el mando enseña cuántas veces han coincidido y,
  cuando lo veas claro, el botón **«Silenciar con la señal»** la activa (`GUIA_SILENCIA=1`). De fábrica solo se apunta.
* **Fotogramas negros (candidato, sin confirmar):** la tele escribe el brillo medio de la imagen unas 8 veces por
  segundo (medido el 2/11/2026). Entre anuncio y anuncio suele haber un instante en negro, así que el hub apunta cuántos
  hay cada minuto y en qué canal (`negros.jsonl` de la carpeta de estado), para compararlo con tus «Silenciar».

### 1b. ↩️ Vuelta al canal al acabar los anuncios
* Si cambias de canal durante los anuncios, la Raspberry devuelve el sonido y, cuando calcula que el corte ha
  terminado, **vuelve sola al canal donde empezaron** (tecleando su número, que aprende del rótulo de la TV).
* La TV tiene **un solo sintonizador**: mientras estás en otro canal no puede ver el primero. Por eso la hora
  de volver se **estima** con lo que duraron los cortes de ese canal otras veces (`DURACION_PUBLI` hasta que
  haya medidas). Un corte se mide cuando se ve su final: con `AD_END_PATTERNS` o al pulsar «Devolver el
  sonido ya» en el móvil.
* Con un marcador de anuncios configurado, al volver **se comprueba**: si siguen, se silencian otra vez.
* En el móvil: cuenta atrás «a Antena 3 en 2:40» con **«Volver ya»** y **«No volver»**.
* Funciona también con el botón **«Silenciar anuncios»** del móvil: marca el principio del corte en ese canal.
* Avisos en la pantalla: «Anuncios en Antena 3 · vuelvo a las 21:34» al cambiar y **«Vuelvo a Antena 3 en 30 s»**
  antes de volver (ver 1d).

### 1c. ⏰ Recordatorios con la guía
* En el móvil, **busca un programa en la guía** (o pulsa «Recordar lo siguiente») y elige qué pasa cuando empiece:
  **poner su canal en la tele**, **mandarte un WhatsApp** o las dos cosas.
* Salta `RECORDATORIO_ANTELACION` segundos antes (60). Dos minutos antes avisa en la pantalla de que va a cambiar.
* Si la tele está en otra app (Netflix, YouTube), abre primero la TDT y luego teclea el número; si está
  apagada, no la enciende y lo deja apuntado. Un recordatorio de cuando el hub estaba parado no se hace tarde.
* El número de cada canal sale del rótulo de la TV o se pregunta una vez y se recuerda.
* Los ejecuta el servicio del silenciador (`panasonic-mute`), que es el que está siempre en marcha.

### 1c-bis. 📺 Más cosas de ver la tele
* **Desde el principio:** si llegas a un programa ya empezado, el mando enseña «⏮ Verlo desde el principio», que
  pulsa el botón azul de la tele (LOVEStv, TDT española). Depende de que el canal siga ofreciéndolo.
* **Seguir una serie o programa:** «⭐ Seguir» en su ficha. Cada vez que salga en la guía (en tus canales y en el
  que lo marcaste, hasta 12 horas antes) se crea solo su recordatorio. Si borras uno, no vuelve.
* **Volumen de cada canal:** recuerda el volumen al que dejas cada canal y lo pone al volver (tras unos segundos
  quieto en el canal; al zapear no aprende nada).
* **Modo noche:** en la franja elegida, el volumen no pasa del tope (y ese tope no se apunta como tu volumen).
* **¿La tienes sin anuncios?:** con una clave gratuita de TMDb, la ficha dice en qué plataformas de suscripción está
  en España y, si la app está en la tele, un botón para abrirla.
* **Despertador** (apagado de fábrica): a la hora y los días elegidos enciende la tele (por red), pone el canal y el
  volumen. Necesita que la tele tenga el encendido por red activado.
* **Apagar la tele si te vas** (apagado de fábrica): si el móvil no está en la WiFi de casa los minutos elegidos y
  la tele sigue encendida, avisa en la pantalla y, si en un minuto nadie toca el volumen ni cambia de canal, la apaga.
* Todo se ajusta en **«🛠️ Opciones del hub»** del mando y se guarda en `ajustes.json` de la carpeta de estado (nunca en el
  repositorio: ahí van la clave de TMDb y el token de Home Assistant).

### 1c-ter. 🏠 Casa (PREPARADO: se activa al rellenar «🛠️ Opciones del hub»)
* **Home Assistant** (API REST con un token de larga duración):
  * **Modo cine:** con una película (por la categoría de la guía) baja las luces elegidas; en los anuncios las deja
    como estaban y al volver las baja otra vez.
  * **Llamada entrante:** con el sensor `phone_state` de la app de Home Assistant en el móvil, silencia la tele y
    avisa «Te llaman al móvil»; al colgar devuelve el sonido.
  * **Avisos de la casa:** Home Assistant llama a `http://<hub>:8080/api/aviso_casa?clave=...&titulo=...&texto=...`
    (la dirección completa sale en «🛠️ Opciones del hub») y el aviso sale en el centro de la tele.
  * **Timbre con cámara:** al sonar, la foto de la cámara en el centro de la tele.
* **Ambilight:** con una cámara que mira la pantalla, una tira LED con WLED y **HyperHDR** en una Raspberry Pi 4
  (la Zero 2 W no llega). La imagen de la TDT y de las apps de la tele no sale por ningún HDMI y la tele no deja
  capturarla, por eso una capturadora HDMI no sirve. El mando lo enciende y lo apaga.
* **DNS antirrastreo con estadísticas** (`core/dns_hub.py`, para la Raspberry; apagado con `DNS_ACTIVO=0`): el hub
  hace de DNS de la tele, contesta 0.0.0.0 a los rastreadores de la TDT y la telemetría, y apunta cada bloqueo con el
  canal o la app que se estaba viendo. La página **`/privacidad`** (botón «📊 Qué ha bloqueado» del mando) lo enseña en
  el móvil: hoy, 7 días, por canal, por dominio y lo último. Nunca sale en la tele. Para usarlo: `DNS_ACTIVO=1`, en la
  tele DNS 1 = IP del hub y DNS 2 = la del router, y quitar el DNS privado de AdGuard (si no, la tele se salta el hub).
  Dominios propios: uno por línea en `dns_bloquear.txt` de la carpeta de estado.
* **Segundo sintonizador TDT por USB** (`core/sintonizador.py`): el mando dice si hay uno conectado. Servirá para ver
  en el móvil el canal de los anuncios y saber de verdad cuándo acaban. Un RTL2832U + R820T2 recibe DVB-T, que es como
  van hoy los canales HD (DVB-T2 solo los UHD); en la Zero 2 W hace falta un adaptador OTG, y un repartidor de antena.

### 1d. 💬 Avisos en la pantalla de la TV
* Mensajes encima de lo que estés viendo (vuelta al canal, recordatorios, apagado nocturno).
* Salen **en el centro de la pantalla y con letra grande** (`AVISOS_TAMANO`, `AVISOS_POSICION`). Los pinta
  **TV Hub Avisos** (`avisos_app/`), una app propia de 17 KB sin icono ni pantalla que solo obedece al ADB: no coge el
  mando ni el foco y se va sola. En el móvil, **«Preparar avisos»** la instala y le da el permiso de mostrarse encima
  de otras apps; **«Probar un aviso»** lo comprueba. Se quita como cualquier app.
* **«Ficha en la tele»** sale igual: una tarjeta en el centro con la carátula, la nota, **en qué minuto vas**, la
  sinopsis y el **reparto, la dirección, la música y quién presenta** (sin la app, se abre en el navegador de la TV,
  también centrada y grande). El reparto sale de la propia guía (líneas «· Reparto:», «· Dirección:»…).
* **Botón del mando para la ficha:** el botón **amarillo** del mando de la tele (o el verde, o «i» dos veces: se
  elige en «🛠️ Opciones del hub») enseña la ficha de lo que echan en el centro de la pantalla; pulsarlo otra vez la quita. Solo
  cuentan las teclas del mando de verdad, no las que manda el hub: se leen del registro del núcleo de la tele
  (`logcat -b kernel`, línea `[GLUE][IR]u8KeyCode`), porque el amarillo no llega a la app de la TDT. Una segunda
  pulsación en los 2 s siguientes no la quita (sin eso, quien vuelve a pulsar por impaciencia la borraba al salir).
* **Con la guía de la tele abierta**, el mismo botón enseña la ficha del programa **marcado** en la guía (de
  cualquier canal o de más tarde), no la de lo que echan. La lee de la pantalla con el «Lector» de la app de avisos
  (`am instrument`, versión 1.3 de la app; si en la tele hay una anterior, el hub la pone al día solo). Tarda unos 4 s.
* **Ficha al cambiar de canal**: la primera vez que llegas a un programa sale su ficha 10 s; si vuelves al mismo
  programa no se repite y si estás zapeando rápido no sale. Se quita en el mando o con `FICHA_AL_CAMBIAR=0`.
* Si en la TV ya estaba **TvOverlay** y no la app propia, se usa TvOverlay (en una esquina y con su letra).
* No toca el sistema de la TV. Se apagan con `AVISOS_EN_TV=0`. La app se compila con
  `python avisos_app/construir_apk.py` (SDK de Android + JDK 17; la clave de firma vive fuera del proyecto).

### 2. 🛡️ Escudo de Privacidad y Bloqueo de Telemetría (Anti-Espionaje)
* **Bloqueo a nivel de sistema operativo:** Activa el DNS Privado seguro (*DoT via AdGuard*) por ADB en la Google TV, bloqueando anuncios y rastreadores sin alterar la red doméstica.
* **Supresión de paquetes espía:** Desactiva los módulos de consentimientos y envío de métricas de diagnóstico de Android TV (`feedback` y `feedbackconsent`).
* **Lista de bloqueo TDT:** Genera una lista negra de dominios de publicidad dirigida española (*Smartclip, Sunmedia, Comscore, HbbTV trackers*) lista para importar en Pi-hole o en el router.

### 3. 🎬 Guía de programación y fichas de cine
* Descarga la guía de la TDT española ([EPG dobleM](https://github.com/davidmuma/EPG_dobleM)) y muestra **qué se emite ahora en el canal que estás viendo**, a qué hora termina y qué viene después.
* Ficha con **nota sobre 10, año, carátula y sinopsis**: de TMDb si pones una clave gratuita (`TMDB_API_KEY`), si no la de la propia guía, y Wikipedia para las búsquedas a mano. Si no hay nota, dice «Sin nota»: no se inventa.
* Distintivo **«🏆 Joya recomendada»** cuando la nota llega a 7,5.

### 4. 📱 Mando a Distancia Web Táctil (Móvil / Tablet)
* Servidor web integrado en el puerto `8080`: abre `http://IP_DE_LA_RASPBERRY:8080` en el móvil.
  **Solo responde al propio equipo y a la red de casa** (ni desde internet, ni a webs que lo llamen con otro
  nombre, ni a órdenes lanzadas desde otra página).
  * **«Silenciar anuncios»** con cuenta atrás y **«Devolver el sonido ya»**.
  * Estado del silenciador automático (activo / en pausa), cortes silenciados hoy y el último.
  * **Ahora en emisión** con su ficha, **«Ficha en la TV»** (la proyecta en la pantalla) y **«A mi WhatsApp»** (opcional, privado).
  * **Recordatorios**: buscar en la guía, recordar lo siguiente, lista de pendientes y lo último que se hizo.
  * **Parrilla**: qué echan ahora y después en tus canales (los que tienen número en tu tele y los de la TDT),
    con **«Poner»** en cada uno. El número que no se sepa se pregunta una vez y se recuerda.
  * **Guía completa**: todos los canales de la guía (primero los tuyos, luego la TDT y el resto) y todos sus
    programas hasta mañana a esta hora, con letra grande y centrada; tocar un programa abre su ficha.
  * **Mensaje en la pantalla de la tele**: lo escribes en el móvil y sale encima de lo que se esté viendo.
  * Volumen, Mute, **Canal +/−**, Guía, cruceta, Volver, Inicio, **Encender / Apagar** (con Wake-on-LAN si se configura la MAC).
  * Solo las apps que **de verdad están instaladas** en la TV.
  * Escribir texto en la TV, temporizador de apagado (30 / 60 min), liberar memoria, DNS antirrastreo.
  * **Salud de la Raspberry**: temperatura y aviso de **alimentación insuficiente** (típico si se alimenta del USB de la TV).

### 5. 🚀 Lanzador de Canales y Aplicaciones
* Acceso en 1 clic para abrir: **YouTube, Netflix, Movistar+, Atresplayer, RTVE Play, Tivify o sintonizar la TDT en directo**.

### 6. ⌨️ Teclado Remoto / Enviar Texto
* Escribe búsquedas de YouTube, títulos o contraseñas complejas desde el teclado de tu PC o móvil directamente en el televisor (sin teclear letra por letra con el mando físico).

### 7. ⏰ Sleep Timer y apagado nocturno
* Programa el apagado de la tele en 15, 30 o 60 minutos con **atenuación progresiva del volumen**.
* **Apagado nocturno** a una hora fija (`APAGADO_NOCTURNO=01:30`) si la TV se ha quedado encendida.

### 8. 🧹 Liberar memoria de la TV
* Cierra las aplicaciones que se quedan en segundo plano para que la TV vaya más fluida.

---

## 📂 Estructura del Repositorio

```text
panasonic-tv-ad-mute/
├── core/
│   ├── tv_manager.py            # Control ADB de la TV (sin shell local; mute con lectura de estado)
│   ├── config.py                # Configuración común (/etc/panasonic-tv-hub/config.env)
│   ├── estado.py                # Estado compartido entre silenciador, mando web y menú
│   ├── epg.py                   # Guía de programación TDT (descarga, «ahora en emisión» y búsqueda)
│   ├── vuelta.py                # Vuelta al canal al acabar los anuncios
│   ├── recordatorios.py         # Recordatorios de la guía (uno por fichero, se disparan una sola vez)
│   ├── avisos_tv.py             # Avisos en la pantalla (app propia TV Hub Avisos; TvOverlay de reserva)
│   ├── senal_guia.py            # Señal de la guía como pista de los anuncios (se apunta junto al botón)
│   ├── ficha_tv.py              # Tarjeta de la ficha: nota, minuto, sinopsis, cartel y reparto
│   ├── ajustes.py               # «🛠️ Opciones del hub» del mando (ajustes.json en la carpeta de estado)
│   ├── rutinas.py               # Volumen por canal, modo noche, despertador y apagar al salir
│   ├── seguir.py                # Seguir una serie: recordatorios automáticos
│   ├── casa.py                  # Home Assistant (luces, llamada, timbre) y HyperHDR (ambilight)
│   ├── presencia.py             # Ping al móvil y MAC de la tele
│   ├── sintonizador.py          # Segundo sintonizador TDT por USB (preparado)
│   ├── whatsapp_privado.py      # Carga el módulo privado de WhatsApp si está
│   ├── media_info.py            # Fichas: TMDb, guía y Wikipedia
│   ├── pi_salud.py              # Temperatura y alimentación de la Raspberry
│   ├── privacy_shield.py        # Bloqueador de telemetría y rastreo TDT
│   └── detectar_tv.py           # Herramienta de test y diagnóstico de compatibilidad
├── menu_tv.py                   # Menú interactivo en terminal (Raspberry Pi y Windows)
├── web_remote.py                # Mando web táctil para el móvil (puerto 8080)
├── INSTALAR_EN_RASPBERRY.bat    # Instala o actualiza la Raspberry desde Windows por SSH
├── COMPATIBILIDAD.md            # Guía detallada de televisores compatibles
├── raspberry_pi/                # Módulo listo para Raspberry Pi Zero 2 W
│   ├── panasonic_ad_mute.py     # Silenciador automático (servicio panasonic-mute)
│   ├── panasonic-mute.service   # Servicio systemd del silenciador
│   ├── panasonic-web.service    # Servicio systemd del mando web
│   ├── install.sh / uninstall.sh
│   ├── tvhub                    # Orden de control (menú, estado, logs, parear, config...)
│   ├── desplegar_desde_windows.py
│   ├── config.env               # Plantilla de configuración
│   └── README.md                # Guía de puesta en marcha paso a paso
├── windows/                     # Módulo para PC con Windows
│   ├── control_tv_windows.py    # Controlador para Windows
│   ├── auto_mute_daemon.py      # Servicio de escucha automática en Windows
│   ├── monitor_anuncios_auto.py # Monitor de eventos en vivo
│   ├── control_tv.bat           # Lanzador del menú interactivo en Windows
│   ├── modo_publi_150s.bat      # Acceso directo de 1 clic para anuncios
│   └── auto_mute_servicio.bat   # Acceso directo al servicio en Windows
├── esp32/                       # Módulo autónomo en microcontrolador de 4 €
│   └── panasonic_esp32_hub.ino  # Código C++ para Arduino IDE
└── docker/                      # Despliegue en contenedor Docker
    ├── Dockerfile
    └── docker-compose.yml
```

---

## 🍓 Puesta en Marcha en Raspberry Pi Zero 2 W

Cuando recibas tu kit **GeeekPi Raspberry Pi Zero 2 W**:

1. Graba **Raspberry Pi OS Lite (64-bit)** con [Raspberry Pi Imager](https://www.raspberrypi.com/software/), con tu Wi-Fi, usuario y SSH activado en los ajustes.
2. Activa la depuración en la TV (Opciones para desarrolladores → Depuración USB).
3. En Windows, doble clic en **`INSTALAR_EN_RASPBERRY.bat`** y acepta en la TV «Permitir siempre».
4. En el móvil: `http://raspberrypi.local:8080`. En la consola de la Pi: `tvhub`.

Guía completa, configuración y órdenes: **[raspberry_pi/README.md](raspberry_pi/README.md)**.

---

## 🪟 Uso en Windows

* **`windows/PanasonicTVHub.exe`** (sin Python): mando web en `http://localhost:8080` y en el móvil
  (`http://<IP del PC>:8080`), con el servicio completo dentro (silenciador, vuelta al canal, avisos y
  recordatorios). **Solo atiende a este PC y a la red de casa.** Al arrancar comprueba el cortafuegos y, si
  falta, abre el puerto solo para la red de casa (Windows pide permiso de administrador la primera vez).
  Detalle en `windows/README.md`.
* **`windows/arrancar_con_windows.bat`**: deja el hub siempre en marcha al iniciar Windows, sin ventanas,
  sin tener que abrir nada (`quitar_del_inicio.bat` lo quita).

Herramientas antiguas con Python:

1. Si no tienes la IP configurada, edita `TV_IP = "192.168.1.132:5555"` en los archivos correspondientes.
2. Haz doble clic en cualquiera de los accesos directos:
   * **`windows/control_tv.bat`**: Abre el menú completo con mando virtual, lanzador de apps, limpiador de RAM y diagnóstico.
   * **`windows/modo_publi_150s.bat`**: Silencia la televisión en 1 clic durante 2 minutos y medio.
   * **`windows/auto_mute_servicio.bat`**: Inicia el detector de anuncios automático en segundo plano.

---

## 📄 Licencia

Este proyecto está bajo licencia [MIT](LICENSE). Código libre y abierto para la comunidad.
