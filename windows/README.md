# Módulo para Windows

Herramientas para controlar la Panasonic Google TV desde Windows mediante ADB.

## Siempre en marcha, sin abrir nada

**`arrancar_con_windows.bat`** (o `PanasonicTVHubServicio.exe --instalar`): copia el hub a
`%LOCALAPPDATA%\PanasonicTVHub`, lo apunta para arrancar al iniciar sesión en Windows **sin ninguna ventana**
y lo pone en marcha ya. Desde entonces `http://localhost:8080` (y el móvil en casa) funcionan siempre.
Para quitarlo: **`quitar_del_inicio.bat`**. Registro en `%APPDATA%\PanasonicTVHub\servicio.log` y `web.log`.
Con el hub en marcha, `PanasonicTVHub.exe` abre solo el menú y usa el que ya está funcionando.

## Aplicación EXE (Doble clic para empezar)

**`PanasonicTVHub.exe`** — Ejecutable todo-en-uno compilado para Windows (9 MB). No requiere Python.
- Mando web en **este PC**: `http://localhost:8080` (se abre solo en el navegador).
- Mando web en **el móvil**, dentro de casa: `http://<IP del PC>:8080` (la consola dice cuál es).
- **Solo atiende a este PC y a la red de casa**: una petición desde internet, una web que llame al mando
  con otro nombre o una orden lanzada desde otra página reciben un «403» y no tocan la TV.
- Lleva dentro el mismo servicio que la Raspberry: silenciador, vuelta al canal, avisos en la pantalla y
  recordatorios de la guía. Su registro va a `%APPDATA%\PanasonicTVHub\servicio.log`.
- Guarda la guía, los recordatorios y los canales aprendidos en `%APPDATA%\PanasonicTVHub`.
- Configuración opcional: un `config.env` junto al EXE (las mismas opciones que en la Raspberry).
- Al salir con «0», devuelve el sonido si lo había quitado.

### Usarlo desde el móvil
**Cada vez que arranca**, el programa comprueba el cortafuegos de Windows. Si falta la regla que abre el
puerto del mando **solo para la red de casa** (o es de otro puerto), la crea: Windows pide permiso de
administrador esa vez; las siguientes ya está y no pregunta. Si se rechaza el permiso, este PC sigue
entrando y el móvil no. `permitir_red_local.bat` hace lo mismo a mano (`permitir_red_local.bat 8090`
para otro puerto).

## Otros archivos incluidos
* `control_tv.bat`: Menú interactivo rápido (requiere Python).
* `modo_publi_150s.bat`: Silencia 2 min y medio y desilencia solo.
* `auto_mute_servicio.bat`: Detector automático de anuncios en segundo plano (antiguo: usa marcadores que
  salen cada 30 s; el EXE ya trae el servicio bueno).
* `permitir_red_local.bat`: abre el puerto del mando solo para la red de casa.
* `monitor_anuncios_auto.py`: Monitor en vivo de eventos HbbTV y de audio.

## Función de Banner en TV

Desde el panel web o el menú interactivo puedes proyectar una ficha de IMDb/Filmaffinity directamente en la pantalla de la televisión:

1. Arranca `PanasonicTVHub.exe` o el servidor web (`python web_remote.py`).
2. En el menú interactivo elige la opción **4 → Proyectar Banner**.
3. O en el panel web del móvil pulsa **«📺 PROYECTAR FICHA IMDB EN LA TELEVISIÓN»**.

El televisor abrirá su navegador interno y mostrará un banner de cine con:
- Póster de la película
- Título, año y nota ⭐
- Sinopsis en castellano
- **Botón especial rojo «🔇 MODO ANUNCIOS»** navegable con el mando

El banner se cierra automáticamente a los 8 segundos.
