@echo off
rem Panasonic TV Hub: deja abrir el mando web de este PC desde el movil, SOLO desde la red de casa.
rem Crea una regla del cortafuegos de Windows para el puerto del mando (8080, u otro: permitir_red_local.bat 8090)
rem limitada a la subred local. Se ejecuta una sola vez; pide permiso de administrador.
setlocal
set PUERTO=%~1
if "%PUERTO%"=="" set PUERTO=8080

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%PUERTO%' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="Panasonic TV Hub (red de casa)" >nul 2>&1
netsh advfirewall firewall add rule name="Panasonic TV Hub (red de casa)" dir=in action=allow protocol=TCP localport=%PUERTO% remoteip=localsubnet profile=any
if errorlevel 1 (
  echo.
  echo No se ha podido crear la regla del cortafuegos.
) else (
  echo.
  echo Listo: el puerto %PUERTO% queda abierto solo para la red de casa.
)
echo.
pause
