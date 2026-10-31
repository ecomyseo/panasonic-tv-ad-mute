# 📺 Guía de Compatibilidad de Televisores

Este proyecto está diseñado para funcionar de forma nativa con **cualquier televisor moderno basado en Android TV / Google TV**, además de los modelos clásicos de **Panasonic con sistema Viera**.

---

## 1. Televisores Compatibles con Control ADB (Nivel 100% Completo)

Todas las televisiones con sistema operativo **Google TV** o **Android TV** (versiones 9, 10, 11, 12, 13 y 14) admiten el control por red (puerto 5555).

### 🏷️ Marcas y Familias Compatibles:

| Fabricante | Modelos / Series | Sistema Operativo |
| :--- | :--- | :--- |
| **Panasonic** | Series MX, MZ, JX, JZ, LX, LZ y modelos Google TV LCD/OLED | Google TV / Android TV |
| **Sony** | Todas las series Bravia (XR, X90, A80, A90, X80, etc.) | Google TV / Android TV |
| **TCL** | Series C (C645, C745, C845), Series P y modelos con Google TV | Google TV / Android TV |
| **Xiaomi** | Xiaomi TV A2, F2, P1, Q2, Mi TV 4S y Xiaomi TV Box | Android TV / Google TV |
| **Philips** | Series Philips Ambilight con Google TV (PML, OLED708, PUS) | Google TV / Android TV |
| **Hisense** | Modelos específicos con Android TV / Google TV (no VIDAA) | Android TV |
| **Nokia / Thomson** | Smart TVs con Android TV oficial | Android TV |
| **Amazon Fire TV** | Fire TV Stick, Fire TV Cube y televisores con Fire OS | Fire OS (Base Android ADB) |

### ⚙️ Cómo activar el control en cualquier Google TV / Android TV:
1. Enciende la TV y entra en **Ajustes (icono de engranaje) > Sistema > Información**.
2. Desciende hasta **«Compilación del SO de Android TV»** (o Número de compilación) y **pulsa 7 veces seguidas el botón OK del mando**. Aparecerá el aviso: *"¡Ya eres desarrollador!"*.
3. Vuelve atrás a **Sistema > Opciones para desarrolladores**.
4. Activa las casillas:
   * **Depuración por USB** (Permite la depuración por red local en el puerto 5555).
   * **Depuración inalámbrica / Depuración por red** (si aparece separada).
5. La primera vez que el script o la Raspberry Pi se conecten, aparecerá un aviso en la pantalla de la TV preguntando: *«¿Permitir depuración por red desde este equipo?»*. Marca la casilla **«Permitir siempre»** y pulsa **Aceptar**.

---

## 2. Televisores Panasonic Clásicos (My Home Screen / Viera)

Modelos anteriores de Panasonic (años 2012 a 2022) que no llevan Google TV, sino el sistema nativo de Panasonic (basado en Firefox OS / My Home Screen):

* **Protocolo:** Utilizan el servicio SOAP en el puerto `55000`.
* **Configuración en la TV:** Entra en **Menú > Red > Configuración de red > Control por red / Aplicación de red** y asegúrate de que esté en **Activado**.
* **Modelos 2018 o posteriores:** Requieren un código PIN de emparejamiento previo.

---

## 3. ¿Cómo saber si tu TV es compatible? (Test Automático)

Hemos incluido un script en la carpeta `core` para verificar cualquier televisor de tu casa automáticamente:

```bash
python core/detectar_tv.py 192.168.1.XXX
```

El script analizará los puertos abiertos de la IP indicada y te dirá exactamente:
* Fabricante y sistema operativo detectado.
* Si el puerto ADB (5555) o SOAP (55000) está disponible.
* El nivel de compatibilidad y las funciones disponibles.
