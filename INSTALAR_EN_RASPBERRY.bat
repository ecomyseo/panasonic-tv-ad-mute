@echo off
chcp 65001 >nul
title Panasonic TV Hub - instalar en la Raspberry Pi
cd /d "%~dp0"
python raspberry_pi\desplegar_desde_windows.py %*
echo.
pause
