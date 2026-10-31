# Guía de Instalación en Raspberry Pi Zero 2 W

Esta guía te explica paso a paso qué hacer cuando recibas tu kit de **Raspberry Pi Zero 2 W**.

---

## 1. Grabar la tarjeta MicroSD (5 minutos)

1. Descarga e instala en tu ordenador la herramienta oficial gratuita: **[Raspberry Pi Imager](https://www.raspberrypi.com/software/)**.
2. Conecta la tarjeta MicroSD a tu ordenador.
3. Abre Raspberry Pi Imager:
   * **Dispositivo:** Elige `Raspberry Pi Zero 2 W`.
   * **Sistema Operativo:** Elige `Raspberry Pi OS (other)` -> **`Raspberry Pi OS Lite (64-bit)`** (la versión Lite no tiene escritorio gráfico, consume menos memoria y vuela).
   * **Almacenamiento:** Elige tu tarjeta MicroSD.
4. Pulsa en **SIGUIENTE**. El programa te preguntará si deseas aplicar la personalización del sistema operativo (pulsa **EDITAR AJUSTES**):
   * **Nombre de usuario y contraseña:** Pon usuario `pi` y una contraseña a tu gusto.
   * **Configurar Wi-Fi:** Pon el nombre de tu red Wi-Fi y la contraseña de casa.
   * **Servicios:** Marca **Habilitar SSH** (con autenticación por contraseña).
5. Dale a **GUARDAR** y luego a **SÍ** para grabar la tarjeta.

---

## 2. Montar y conectar la Raspberry Pi Zero 2 W

1. Coloca los disipadores térmicos en el chip principal y encaja la Raspberry Pi en la caja de aluminio pasivo de GeekPi.
2. Introduce la tarjeta MicroSD en la ranura.
3. Conecta el cable de alimentación al puerto micro-USB de la Pi (marcado como `PWR IN`). 
   * *Consejo:* Puedes enchufarlo a un puerto USB de tu propia televisión Panasonic (así se enciende cuando enciendes la tele) o usar el cargador incluido en el kit.
4. Espera 1 minuto a que termine de arrancar y se conecte al Wi-Fi de tu casa.

---

## 3. Instalar el servicio silenciador (1 solo comando)

1. Abre una consola de comandos en tu ordenador con Windows (CMD o PowerShell) y conéctate a la Raspberry Pi por SSH:
   ```cmd
   ssh pi@raspberrypi.local
   ```
   *(Introduce la contraseña que configuraste al grabar la SD).*

2. Clona este repositorio y entra en la carpeta:
   ```bash
   git clone https://github.com/ecomyseo/panasonic-tv-ad-mute.git
   cd panasonic-tv-ad-mute/raspberry_pi
   ```

3. Si la IP de tu TV cambió, edita `config.env`:
   ```bash
   nano config.env
   ```

4. Ejecuta el instalador automático:
   ```bash
   chmod +x install.sh
   sudo ./install.sh
   ```

¡Y listo! El servicio ya estará funcionando en segundo plano las 24 horas del día. Cada vez que la televisión reciba un bloque publicitario en la TDT, la Raspberry Pi silenciará la televisión automáticamente.
