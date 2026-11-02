#!/usr/bin/env python3
"""
Construye TVHubAvisos.apk sin Gradle: aapt2 + javac + d8 + zipalign + apksigner.
    python construir_apk.py

Necesita el SDK de Android (ANDROID_HOME, por defecto C:\\dev\\android-sdk) con build-tools y la plataforma 34,
y un JDK 17 (javac y keytool en el PATH o en JAVA_HOME).

La clave de firma vive FUERA del repositorio (TVHUB_CLAVE_DIR, por defecto C:\\dev-tools\\claves\\tvhub_avisos):
si no existe se crea la primera vez. Sin esa misma clave no se puede ACTUALIZAR la app ya instalada en la TV
(habría que quitarla antes con «adb uninstall es.gmartos.tvhub.avisos»).
"""

import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "TVHubAvisos.apk")
VERSION_CODIGO = 2
VERSION_NOMBRE = "1.1"
SDK_MIN, SDK_OBJETIVO = 26, 34
SDK = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or r"C:\dev\android-sdk"
CLAVES = os.environ.get("TVHUB_CLAVE_DIR") or r"C:\dev-tools\claves\tvhub_avisos"


def herramienta(nombre):
    carpeta = os.path.join(SDK, "build-tools")
    versiones = sorted((v for v in os.listdir(carpeta) if os.path.isdir(os.path.join(carpeta, v))),
                       key=lambda v: [int(x) if x.isdigit() else 0 for x in v.replace("-", ".").split(".")])
    for v in reversed(versiones):
        for ext in ("", ".exe", ".bat"):
            ruta = os.path.join(carpeta, v, nombre + ext)
            if os.path.exists(ruta):
                return ruta
    sys.exit(f"Falta {nombre} en {carpeta}")


def jdk(nombre):
    if os.environ.get("JAVA_HOME"):
        for ext in (".exe", ""):
            ruta = os.path.join(os.environ["JAVA_HOME"], "bin", nombre + ext)
            if os.path.exists(ruta):
                return ruta
    ruta = shutil.which(nombre)
    if not ruta:
        sys.exit(f"Falta {nombre} (instala un JDK 17)")
    return ruta


def correr(*orden):
    r = subprocess.run([str(o) for o in orden], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"Ha fallado: {os.path.basename(str(orden[0]))}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def clave():
    os.makedirs(CLAVES, exist_ok=True)
    almacen = os.path.join(CLAVES, "tvhub_avisos.jks")
    contrasena = os.path.join(CLAVES, "contrasena.txt")
    if not os.path.exists(almacen):
        with open(contrasena, "w", encoding="ascii") as f:
            f.write(secrets.token_urlsafe(24))
        texto = open(contrasena, encoding="ascii").read().strip()
        correr(jdk("keytool"), "-genkeypair", "-keystore", almacen, "-storepass", texto, "-keypass", texto,
               "-alias", "tvhub", "-keyalg", "RSA", "-keysize", "2048", "-validity", "36500",
               "-dname", "CN=Panasonic TV Hub, O=Ecom Experts, C=ES")
        print(f"Clave de firma nueva en {CLAVES} (guárdala: sin ella no se puede actualizar la app)")
    return almacen, contrasena


def main():
    plataforma = os.path.join(SDK, "platforms", f"android-{SDK_OBJETIVO}", "android.jar")
    if not os.path.exists(plataforma):
        sys.exit(f"Falta la plataforma android-{SDK_OBJETIVO}: {plataforma}")
    trabajo = tempfile.mkdtemp(prefix="tvhub_apk_")
    try:
        base = os.path.join(trabajo, "base.apk")
        correr(herramienta("aapt2"), "link", "-o", base, "-I", plataforma,
               "--manifest", os.path.join(AQUI, "AndroidManifest.xml"),
               "--min-sdk-version", SDK_MIN, "--target-sdk-version", SDK_OBJETIVO,
               "--version-code", VERSION_CODIGO, "--version-name", VERSION_NOMBRE)
        fuentes = [os.path.join(r, f) for r, _, fs in os.walk(os.path.join(AQUI, "src")) for f in fs
                   if f.endswith(".java")]
        clases = os.path.join(trabajo, "clases")
        os.makedirs(clases)
        correr(jdk("javac"), "-encoding", "UTF-8", "--release", "8", "-classpath", plataforma,
               "-d", clases, "-Xlint:-options", *fuentes)
        compiladas = [os.path.join(r, f) for r, _, fs in os.walk(clases) for f in fs if f.endswith(".class")]
        dex = os.path.join(trabajo, "dex")
        os.makedirs(dex)
        correr(herramienta("d8"), "--release", "--min-api", SDK_MIN, "--lib", plataforma, "--output", dex,
               *compiladas)
        sin_alinear = os.path.join(trabajo, "sin_alinear.apk")
        shutil.copy(base, sin_alinear)
        with zipfile.ZipFile(sin_alinear, "a", zipfile.ZIP_DEFLATED) as z:
            z.write(os.path.join(dex, "classes.dex"), "classes.dex")
        alineado = os.path.join(trabajo, "alineado.apk")
        correr(herramienta("zipalign"), "-p", "-f", "4", sin_alinear, alineado)
        almacen, contrasena = clave()
        correr(herramienta("apksigner"), "sign", "--ks", almacen, "--ks-pass", f"file:{contrasena}",
               "--ks-key-alias", "tvhub", "--out", SALIDA, alineado)
        correr(herramienta("apksigner"), "verify", SALIDA)
        if os.path.exists(SALIDA + ".idsig"):
            os.remove(SALIDA + ".idsig")
    finally:
        shutil.rmtree(trabajo, ignore_errors=True)
    print(f"APK lista: {SALIDA} ({os.path.getsize(SALIDA)} bytes, versión {VERSION_NOMBRE})")


if __name__ == "__main__":
    main()
