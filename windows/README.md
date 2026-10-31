# Módulo para Windows

Herramientas para controlar la Panasonic Google TV desde Windows mediante ADB.

## Aplicación EXE (Doble clic para empezar)

**`PanasonicTVHub.exe`** — Ejecutable todo-en-uno compilado para Windows (8.4 MB).
- Inicia automáticamente el servidor web en `http://localhost:8080`.
- Abre el navegador con el panel de control.
- Lanza el menú interactivo en la misma ventana.
- No requiere Python instalado.

## Otros archivos incluidos
* `control_tv.bat`: Menú interactivo rápido (requiere Python).
* `modo_publi_150s.bat`: Silencia 2 min y medio y desilencia solo.
* `auto_mute_servicio.bat`: Detector automático de anuncios en segundo plano.
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
