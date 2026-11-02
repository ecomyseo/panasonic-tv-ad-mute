@echo off
rem Panasonic TV Hub: arranca solo al iniciar Windows, sin ninguna ventana, y se pone en marcha ya.
rem Despues: http://localhost:8080 en este PC y http://<IP del PC>:8080 en el movil (solo en casa).
"%~dp0PanasonicTVHubServicio.exe" --instalar
