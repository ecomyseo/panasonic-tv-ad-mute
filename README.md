# 📺 Panasonic Google TV Smart Hub & Ad-Mute Suite

Sistema integral de automatización, mando a distancia inteligente y silenciador automático de publicidad para televisores **Panasonic con Google TV / Android 14** (y Viera).

Diseñado específicamente para ejecutarse de forma autónoma en una **Raspberry Pi Zero 2 W** (24/7 de bajo consumo), en tu ordenador con **Windows**, o mediante un microcontrolador **ESP32**.

---

## 🌟 Características Principales

1. **🔇 Silenciador Automático de Publicidad:**
   * Monitorea la señal del sintonizador interno mediante eventos de sistema **HbbTV / DVB-TA** (`exchangeType==28`, `getHBBTVBannerControl`) y conmutaciones del amplificador de audio (`AUDIO_AMP`).
   * Silencia la TV en el milisegundo exacto en que entra el bloque de anuncios y restaura el sonido automáticamente al terminar el corte.
   * Cuenta con un *Watchdog* de seguridad para garantizar que la televisión nunca se quede silenciada permanentemente.

2. **📱 Mando a Distancia Web Táctil (Móvil):**
   * Servidor web integrado en el puerto `8080`.
   * Abre `http://IP_DE_LA_RASPBERRY:8080` desde el navegador de tu móvil o tablet:
     * Botón gigante **«MODO PUBLICIDAD (150s)»** con cuenta regresiva.
     * Control de volumen (`Vol +`, `Vol -`, `Mute`).
     * Cruceta de navegación táctil (Arriba, Abajo, Izquierda, Derecha, OK, Volver, Home, Apagar).
     * Indicador en tiempo real del canal de televisión sintonizado.

3. **🚀 Lanzador de Canales y Aplicaciones:**
   * Acceso en 1 clic para abrir: **YouTube, Netflix, Movistar+, Atresplayer, RTVE Play, Tivify o sintonizar la TDT en directo**.

4. **⌨️ Teclado Remoto / Enviar Texto:**
   * Escribe búsquedas de YouTube, títulos o contraseñas Wi-Fi complejas desde el teclado de tu PC o móvil directamente en el televisor (sin la molestia de teclear letra por letra con el mando físico).

5. **⏰ Sleep Timer Inteligente (Apagado Nocturno):**
   * Programa el apagado de la tele en 15, 30 o 60 minutos con **atenuación progresiva del volumen** durante los últimos minutos para conciliar el sueño.

6. **🧹 Acelerador y Limpieza de RAM de la TV:**
   * Cierra aplicaciones secundarias colgadas en segundo plano y libera la memoria caché de Android 14 para mantener la TV fluida y rápida.

7. **📊 Diagnóstico y Estado en Tiempo Real:**
   * Consulta el canal sintonizado, memoria RAM libre, espacio en almacenamiento interno, temperatura y tiempo de actividad.

---

## 📂 Estructura del Repositorio

```text
panasonic-tv-ad-mute/
├── core/
│   └── tv_manager.py            # Librería principal de control ADB para Android TV
├── menu_tv.py                   # Menú interactivo en terminal (Raspberry Pi y Windows)
├── web_remote.py                # Servidor Web y mando a distancia para el móvil (puerto 8080)
├── raspberry_pi/                # Módulo listo para Raspberry Pi Zero 2 W
│   ├── panasonic_ad_mute.py     # Demonio de escucha continua y silenciado automático
│   ├── panasonic-mute.service   # Servicio systemd de arranque automático 24/7
│   ├── install.sh               # Instalador automático en 1 solo paso
│   ├── config.env               # Configuración de IP y tiempos
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

1. Graba **Raspberry Pi OS Lite (64-bit)** en tu MicroSD usando [Raspberry Pi Imager](https://www.raspberrypi.com/software/), configurando tu Wi-Fi y usuario SSH en los ajustes del instalador.
2. Conecta la Raspberry Pi por USB (puedes alimentarla desde un puerto USB de la propia TV).
3. Conéctate por SSH y clona este repositorio:
   ```bash
   git clone https://github.com/ecomyseo/panasonic-tv-ad-mute.git
   cd panasonic-tv-ad-mute/raspberry_pi
   chmod +x install.sh
   sudo ./install.sh
   ```
4. Para abrir el menú interactivo con todas las funciones:
   ```bash
   python3 ../menu_tv.py
   ```
5. Para abrir el mando web desde tu móvil:
   * Abre `http://IP_DE_TU_RASPBERRY:8080` en cualquier navegador de tu red de casa.

---

## 🪟 Uso en Windows

1. Si no tienes la IP configurada, edita `TV_IP = "192.168.1.132:5555"` en los archivos correspondientes.
2. Haz doble clic en cualquiera de los accesos directos:
   * **`windows/control_tv.bat`**: Abre el menú completo con mando virtual, lanzador de apps, limpiador de RAM y diagnóstico.
   * **`windows/modo_publi_150s.bat`**: Silencia la televisión en 1 clic durante 2 minutos y medio.
   * **`windows/auto_mute_servicio.bat`**: Inicia el detector de anuncios automático en segundo plano.

---

## 🔌 Uso con ESP32 (Microcontrolador de 4 €)

1. Abre `esp32/panasonic_esp32_hub.ino` con el **Arduino IDE**.
2. Introduce tu red Wi-Fi y contraseña.
3. Conecta el ESP32 por USB y súbelo.
4. El botón `BOOT` de la placa silenciará la TV con una cuenta regresiva de 150 segundos y levantará una web en su IP local.

---

## 📄 Licencia

Este proyecto está bajo licencia [MIT](LICENSE). Código libre y abierto para la comunidad.
