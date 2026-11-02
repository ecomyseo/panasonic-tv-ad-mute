# -*- mode: python ; coding: utf-8 -*-
# Dos programas:
#   PanasonicTVHub.exe          con consola: el menú
#   PanasonicTVHubServicio.exe  sin ventana: el hub en segundo plano (--instalar lo pone al iniciar Windows)

OCULTOS = ['tv_manager', 'media_info', 'privacy_shield', 'config', 'estado', 'epg', 'pi_salud', 'vuelta',
           'recordatorios', 'avisos_tv', 'senal_guia', 'whatsapp_privado', 'cortafuegos_windows', 'panasonic_ad_mute',
           'web_remote', 'menu_tv', 'app_launcher']


def analisis(guion):
    return Analysis(
        [guion],
        pathex=['core', 'raspberry_pi'],
        binaries=[],
        datas=[('core', 'core'), ('avisos_app/TVHubAvisos.apk', 'avisos_app')],
        hiddenimports=OCULTOS,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
        optimize=0,
    )


def programa(a, nombre, consola):
    pyz = PYZ(a.pure)
    return EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=nombre,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=consola,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )


menu = programa(analisis('app_launcher.py'), 'PanasonicTVHub', True)
servicio = programa(analisis('servicio_windows.py'), 'PanasonicTVHubServicio', False)
