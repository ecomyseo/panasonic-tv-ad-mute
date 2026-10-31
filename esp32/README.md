# Módulo ESP32

Código autónomo para microcontrolador ESP32 (programable con Arduino IDE).

## Características
* Botón físico (`BOOT` / GPIO 0) para silenciar la TV con temporizador de 150 segundos.
* Servidor web en la IP del ESP32 (`http://IP_DEL_ESP32/mute`) para activar Mute desde cualquier navegador.
* Soporte para conectar un sensor de sonido analógico en el pin 34.
