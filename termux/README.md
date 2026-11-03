# 📱 Panasonic TV Hub en un móvil Android viejo

Un móvil Android que ya no usas puede hacer de hub las 24 horas, igual que una Raspberry Pi: silencia los anuncios,
vuelve al canal, enseña las fichas con el botón amarillo, tiene el mando web, los recordatorios y lo demás.
**Sin root, sin cables y sin comprar nada.** Probado en un UMIDIGI S5 Pro con Android 10 (3/11/2026).

Lo único que no puede hacer es el **DNS antirrastreo**: necesita el puerto 53, y en un móvil sin root no se puede
abrir. Todo lo demás funciona igual.

## Lo que hace falta

- Un móvil con **Android 7 o superior**, conectado al **mismo wifi** que la tele.
- La tele con la **depuración por red** activada (Ajustes → Sistema → Opciones para desarrolladores →
  «Depuración USB» y, si aparece, «Depuración por red»).
- Un cargador para el móvil (lee también «[La batería](#-la-batería-siempre-enchufado)»).

No hace falta activar nada de desarrollador en el móvil: todo se instala desde el propio móvil.

## Paso a paso

### 1. Instalar Termux y Termux:Boot (de F-Droid)

En el navegador del móvil:

1. Abre [f-droid.org/es/packages/com.termux](https://f-droid.org/es/packages/com.termux/), baja hasta
   «Descargar APK» e instálalo. Si pregunta, deja instalar apps de **origen desconocido** desde el navegador.
2. Haz lo mismo con [f-droid.org/es/packages/com.termux.boot](https://f-droid.org/es/packages/com.termux.boot/)
   (**Termux:Boot**, para que el hub arranque solo cuando se encienda el móvil) y **ábrelo una vez**.

> Los dos tienen que venir de F-Droid. El Termux de la Play Store está anticuado y no se entiende con el
> Termux:Boot de F-Droid.

### 2. Instalar el hub

Abre **Termux**, espera a que termine de prepararse la primera vez, y escribe estas órdenes **una por una**,
pulsando Intro después de cada una:

```
pkg upgrade -y
```

```
pkg install -y git
```

```
git clone https://github.com/ecomyseo/panasonic-tv-ad-mute
```

```
bash panasonic-tv-ad-mute/termux/instalar.sh
```

Si la tele no tiene la IP de la plantilla (`192.168.1.132`), añádela al final de la última orden:
`bash panasonic-tv-ad-mute/termux/instalar.sh 192.168.1.50`.

El instalador va enseñando del paso **1/5** al **5/5** y al final pone **«Listo»** con la dirección del mando web.
Tarda unos minutos; lo que más, poner Termux al día.

### 3. Permitir el móvil en la tele

La primera vez, la tele enseña **«¿Permitir la depuración?»**: acéptalo con el mando marcando
**«Permitir siempre»**. Si no sale, apaga y enciende la tele.

### 4. Que Android no lo cierre

En los **Ajustes del móvil** → Aplicaciones → **Termux** → Batería → **Sin restricciones** (en algunos móviles:
«No optimizar»). Sin esto, Android lo para al rato de apagar la pantalla.

### 5. Usarlo

- Mando web: **`http://<IP del móvil>:8080`** desde cualquier móvil o tablet de casa. La IP sale al final de la
  instalación. Conviene fijarla en el router («reserva DHCP») para que no cambie.
- Si antes tenías el hub en un PC o en una Raspberry, **apágalo allí**: dos hubs a la vez harían todo dos veces.

## Gastar lo mínimo de luz

El hub ya viene preparado para gastar poco:

- **La tele filtra lo que manda.** De las ~357 líneas por segundo que escribe la tele, el hub solo necesita ~7.
  El filtro se hace en la propia tele (`logcat … | grep --line-buffered -F`), así que por el wifi y por el móvil
  solo pasa lo útil (medido el 3/11/2026).
- **El volumen se mira al tocarlo en el mando**, no cada pocos segundos (y por si acaso, cada 20 s).
- **Con la tele apagada no se le pregunta nada**: el hub espera y se vuelve a conectar al encenderla.

Y en el móvil, una vez instalado:

- **Pantalla:** brillo al mínimo y que se apague a los 15 o 30 segundos.
- **Modo avión con el wifi encendido**: quita la red móvil, que es lo que más gasta si tiene SIM.
- **Apaga** el Bluetooth, la ubicación (GPS), la sincronización automática y el NFC.
- **Desinstala o desactiva** las apps que no uses (redes sociales, juegos, tiendas…): son las que despiertan el móvil.
- Que **solo** se quede abierto Termux.

## 🔋 La batería, siempre enchufado

Un móvil enchufado día y noche al 100 % desgasta la batería y, con los años, puede hincharse. Sin root, el móvil
no puede dejar de cargar por sí mismo. Mientras no haya otra cosa:

- Déjalo **en un sitio fresco y ventilado**, fuera de la funda y sin nada encima.
- Usa un **cargador flojo** (5 V y 1 A, el de un móvil viejo): calienta menos que uno de carga rápida.
- Si ves la batería **abombada** (la tapa se levanta, la pantalla se despega), desenchúfalo y no lo uses.

Lo que de verdad lo arregla es que el hub corte la corriente al 80 % y la devuelva al 40 %. Para eso hace falta un
enchufe que se pueda apagar por wifi (por ejemplo un Shelly Plug S) o un relé; **todavía no está hecho**.

## Órdenes útiles (en Termux)

| Para | Orden |
|---|---|
| Ponerlo al día (sin tocar los ajustes) | `bash ~/panasonic-tv-hub/termux/instalar.sh` |
| Pararlo | `~/panasonic-tv-hub/termux/parar.sh` |
| Arrancarlo | `~/panasonic-tv-hub/termux/arrancar.sh` |
| Ver qué hace | `tail -20 ~/.panasonic-tv-hub/silenciador.log` |
| Ajustes a mano | `nano ~/.panasonic-tv-hub/config.env` (y después parar y arrancar) |

Los ajustes y el estado viven en `~/.panasonic-tv-hub`; el programa, en `~/panasonic-tv-hub`. Actualizar cambia
solo el programa.

## Si algo falla

| Lo que pasa | Qué hacer |
|---|---|
| `cannot locate symbol "SSL_…"` al usar `curl` o `pkg` | Termux recién instalado y sin poner al día: `pkg upgrade -y` y repetir. |
| `WARNING: apt does not have a stable CLI interface` | No es un error: sigue esperando. |
| `bash: …instalar.sh: No such file or directory` | La orden `git clone` no terminó bien: repítela y comprueba con `ls` que aparece `panasonic-tv-ad-mute`. |
| No encuentro la barra vertical (`\|`) en el teclado | Las órdenes de arriba no la necesitan. En el teclado de Google está en «?123» → «=\\<». |
| El mando web no abre | Comprueba la IP del móvil (Ajustes → Wifi → la red) y que el móvil y el que abre el mando están en el mismo wifi. |
| El hub dice que la tele no responde | La tele apagada, o la depuración por red desactivada, o falta aceptar «Permitir la depuración» en la tele. |
| Se para al rato de apagar la pantalla | Falta el paso 4 (batería sin restricciones). En Android 12 o más nuevo, además, Android cierra procesos de Termux; desde un PC con ADB: `adb shell device_config put activity_manager max_phantom_processes 2147483647`. |
| No arranca solo al reiniciar el móvil | Abre una vez Termux:Boot, y que Termux y Termux:Boot vengan los dos de F-Droid. |

## Qué hay en esta carpeta

- `instalar.sh` — instala o pone al día: python y adb, el hub, los ajustes en `~/.panasonic-tv-hub`, el arranque
  con Termux:Boot, y lo arranca. Se puede lanzar desde una copia clonada (usa esa) o suelto (lo baja de GitHub).
- `arrancar.sh` — arranca el silenciador y el mando web, cada uno vigilado: si se cae, se vuelve a arrancar a los 10 s.
- `parar.sh` — lo para todo.
