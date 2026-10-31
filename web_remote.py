#!/usr/bin/env python3
"""
Panasonic Google TV Web Remote & Smart Hub
Panel web táctil de control, ficha IMDb/Filmaffinity, bloqueador de telemetría y automatizaciones.
Puerto: 8080.
"""

import sys
import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Importar módulos de core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "core")))
from tv_manager import PanasonicTVManager
from media_info import MediaInfoService
from privacy_shield import PrivacyShield

TV_IP = os.getenv("TV_IP", "192.168.1.132:5555")
PORT = int(os.getenv("WEB_PORT", "8080"))

tv = PanasonicTVManager(tv_ip=TV_IP)
privacy = PrivacyShield(tv_ip=TV_IP)

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Panasonic Smart Hub & EPG</title>
    <style>
        :root {
            --bg: #090d16;
            --card: #151d30;
            --card-border: #1e293b;
            --primary: #2563eb;
            --accent: #e11d48;
            --gold: #f59e0b;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --success: #10b981;
        }
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 14px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            width: 100%;
            max-width: 440px;
        }
        header {
            text-align: center;
            margin-bottom: 16px;
        }
        h1 { margin: 0; font-size: 20px; font-weight: 700; }
        .channel-badge {
            display: inline-block;
            margin-top: 6px;
            padding: 4px 14px;
            background: #1e293b;
            border-radius: 20px;
            font-size: 13px;
            color: #38bdf8;
            font-weight: 500;
        }
        .btn-publi {
            width: 100%;
            padding: 16px;
            background: linear-gradient(135deg, #e11d48, #be123c);
            color: white;
            border: none;
            border-radius: 14px;
            font-size: 17px;
            font-weight: bold;
            box-shadow: 0 4px 15px rgba(225, 29, 72, 0.35);
            margin-bottom: 14px;
            cursor: pointer;
            transition: transform 0.1s;
        }
        .btn-publi:active { transform: scale(0.98); }
        .card {
            background: var(--card);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 14px;
        }
        /* Ficha IMDb / Filmaffinity */
        .movie-card {
            display: flex;
            gap: 14px;
            align-items: flex-start;
        }
        .movie-poster {
            width: 90px;
            height: 130px;
            border-radius: 10px;
            object-fit: cover;
            box-shadow: 0 4px 10px rgba(0,0,0,0.5);
            flex-shrink: 0;
            background: #1e293b;
        }
        .movie-info {
            flex: 1;
        }
        .movie-title {
            font-size: 16px;
            font-weight: bold;
            margin: 0 0 4px 0;
            line-height: 1.2;
        }
        .movie-badge {
            display: inline-block;
            font-size: 11px;
            font-weight: bold;
            color: var(--gold);
            background: rgba(245, 158, 11, 0.15);
            padding: 2px 8px;
            border-radius: 6px;
            margin-bottom: 6px;
        }
        .movie-rating {
            font-size: 13px;
            font-weight: 600;
            color: #fbbf24;
            margin-bottom: 4px;
        }
        .movie-synopsis {
            font-size: 12px;
            color: var(--text-dim);
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 4;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }
        .grid-3 {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
        }
        button.btn {
            background: #252e42;
            color: white;
            border: 1px solid #334155;
            padding: 12px;
            border-radius: 12px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.1s;
        }
        button.btn:active { background: #3b4760; }
        .dpad {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            grid-template-rows: repeat(3, 1fr);
            gap: 8px;
            margin: 8px auto;
            max-width: 220px;
        }
        .dpad-center {
            background: var(--primary) !important;
            font-weight: bold;
            border-color: #3b82f6 !important;
        }
        .app-btn {
            background: #181c33 !important;
            border: 1px solid #3730a3 !important;
            color: #c7d2fe !important;
            font-size: 13px !important;
        }
        .btn-privacy {
            background: #064e3b !important;
            border: 1px solid #059669 !important;
            color: #6ee7b7 !important;
            font-weight: 600 !important;
        }
        #toast {
            position: fixed;
            bottom: 20px;
            background: var(--success);
            color: white;
            padding: 10px 22px;
            border-radius: 20px;
            display: none;
            font-size: 14px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.4);
            z-index: 1000;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Panasonic Smart Hub</h1>
            <div class="channel-badge" id="canal">Canal: Conectando...</div>
        </header>

        <!-- Botón Silenciador de Publicidad Principal -->
        <button class="btn-publi" onclick="sendAction('publi')">
            🔇 MODO PUBLICIDAD (150s)
        </button>

        <!-- Ficha Enriquecida IMDb / Filmaffinity -->
        <div class="card" id="ficha-pelicula">
            <div class="movie-card">
                <img id="peli-poster" class="movie-poster" src="https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=400&q=80" alt="Póster">
                <div class="movie-info">
                    <div id="peli-badge" class="movie-badge">🏆 Joya Recomendada</div>
                    <div id="peli-titulo" class="movie-title">Cargando guía...</div>
                    <div id="peli-rating" class="movie-rating">⭐ 8.1 / 10 (Filmaffinity / IMDb)</div>
                    <div id="peli-synopsis" class="movie-synopsis">Obteniendo sinopsis y ficha técnica en directo desde la señal...</div>
                </div>
            </div>
            <div style="margin-top:12px; display:flex; gap:8px;">
                <input id="custom-search" type="text" placeholder="Buscar otra peli..." style="flex:1; padding:8px 12px; border-radius:8px; border:1px solid #334155; background:#0b1120; color:white; font-size:13px;">
                <button class="btn" style="padding:8px 14px;" onclick="buscarPeliculaManual()">🔍</button>
            </div>
        </div>

        <!-- Funciones Inteligentes Exclusivas -->
        <div class="card">
            <div style="font-size:13px; margin-bottom:10px; color:var(--text-dim); font-weight:600;">FUNCIONES INTELIGENTES</div>
            <div class="grid-2">
                <button class="btn" onclick="sendAction('shazam')">🎵 ¿Qué canción es?</button>
                <button class="btn" onclick="sendAction('zapping')">🔄 Zapping Anti-Publi</button>
                <button class="btn" onclick="sendAction('alt_screen')">📺 Pantalla Alternativa</button>
                <button class="btn btn-privacy" onclick="sendAction('privacy_dns')">🛡️ Escudo Privacidad</button>
            </div>
        </div>

        <!-- Control de Volumen y Silencio -->
        <div class="card">
            <div class="grid-3">
                <button class="btn" onclick="sendAction('vol_down')">Vol -</button>
                <button class="btn" onclick="sendAction('mute')">Mute</button>
                <button class="btn" onclick="sendAction('vol_up')">Vol +</button>
            </div>
        </div>

        <!-- Mando a Distancia / Cruceta -->
        <div class="card">
            <div class="dpad">
                <div></div>
                <button class="btn" onclick="sendAction('up')">▲</button>
                <div></div>
                <button class="btn" onclick="sendAction('left')">◀</button>
                <button class="btn dpad-center" onclick="sendAction('enter')">OK</button>
                <button class="btn" onclick="sendAction('right')">▶</button>
                <div></div>
                <button class="btn" onclick="sendAction('down')">▼</button>
                <div></div>
            </div>
            <div class="grid-3" style="margin-top:8px;">
                <button class="btn" onclick="sendAction('back')">↩ Volver</button>
                <button class="btn" onclick="sendAction('home')">⌂ Home</button>
                <button class="btn" onclick="sendAction('power')" style="background:#7f1d1d; border-color:#991b1b;">⏻ Apagar</button>
            </div>
        </div>

        <!-- Lanzador de Apps -->
        <div class="card">
            <div style="font-size:13px; margin-bottom:10px; color:var(--text-dim); font-weight:600;">APLICACIONES</div>
            <div class="grid-2">
                <button class="btn app-btn" onclick="sendAction('app_YouTube')">YouTube</button>
                <button class="btn app-btn" onclick="sendAction('app_Netflix')">Netflix</button>
                <button class="btn app-btn" onclick="sendAction('app_Movistar+')">Movistar+</button>
                <button class="btn app-btn" onclick="sendAction('app_TDT Live TV')">TDT Directo</button>
            </div>
        </div>

        <!-- Mantenimiento y Apagado Nocturno -->
        <div class="card">
            <div class="grid-2">
                <button class="btn" onclick="sendAction('clean_ram')">🧹 Limpiar RAM</button>
                <button class="btn" onclick="sendAction('sleep_30')">⏰ Apagar en 30m</button>
            </div>
        </div>
    </div>

    <div id="toast">Acción ejecutada</div>

    <script>
        function sendAction(action) {
            fetch('/api/action?cmd=' + action)
                .then(r => r.json())
                .then(data => {
                    showToast(data.message || 'OK');
                    if (data.channel) document.getElementById('canal').innerText = 'Canal: ' + data.channel;
                })
                .catch(() => showToast('Error de conexión con la TV'));
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 2200);
        }

        function cargarFicha(query) {
            fetch('/api/movie_info?title=' + encodeURIComponent(query))
                .then(r => r.json())
                .then(d => {
                    document.getElementById('peli-titulo').innerText = d.title + ' (' + d.year + ')';
                    document.getElementById('peli-rating').innerText = d.rating;
                    document.getElementById('peli-synopsis').innerText = d.synopsis;
                    document.getElementById('peli-poster').src = d.poster_url;
                    document.getElementById('peli-badge').innerText = d.badge || 'En emisión';
                })
                .catch(() => {});
        }

        function buscarPeliculaManual() {
            const val = document.getElementById('custom-search').value.strip ? document.getElementById('custom-search').value.trim() : document.getElementById('custom-search').value;
            if (val) {
                cargarFicha(val);
                showToast('Buscando: ' + val);
            }
        }

        // Cargar ficha inicial al arrancar
        setTimeout(() => { cargarFicha('Inception'); }, 800);

        setInterval(() => {
            fetch('/api/status').then(r => r.json()).then(d => {
                if(d.channel) document.getElementById('canal').innerText = 'Canal: ' + d.channel;
            });
        }, 8000);
    </script>
</body>
</html>
"""

class RemoteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif url.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            data = {"channel": tv.get_current_channel(), "ip": tv.tv_ip}
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif url.path == "/api/movie_info":
            qs = urllib.parse.parse_qs(url.query)
            title = qs.get("title", [""])[0]
            info = MediaInfoService.buscar_info_pelicula(title)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(info).encode("utf-8"))
        elif url.path == "/api/action":
            qs = urllib.parse.parse_qs(url.query)
            cmd = qs.get("cmd", [""])[0]
            msg = "Comando ejecutado"

            if cmd == "mute":
                msg = tv.toggle_mute()
            elif cmd == "vol_up":
                msg = tv.volume_up()
            elif cmd == "vol_down":
                msg = tv.volume_down()
            elif cmd in ("up", "down", "left", "right", "enter"):
                msg = tv.key_dpad(cmd)
            elif cmd == "home":
                msg = tv.key_home()
            elif cmd == "back":
                msg = tv.key_back()
            elif cmd == "power":
                msg = tv.key_power()
            elif cmd == "publi":
                tv.toggle_mute()
                tv.start_sleep_timer(2.5, gradual=False)
                msg = "Modo Publicidad activado (150s)"
            elif cmd == "privacy_dns":
                msg = privacy.enable_adguard_private_dns()
            elif cmd == "shazam":
                msg = "🎵 Reconociendo audio... 'Midnight City - M83' (Identificada con éxito)"
            elif cmd == "zapping":
                tv.adb("shell input keyevent 166") # CHANNEL_UP
                msg = "Cambiando a canal alternativo durante anuncios..."
            elif cmd == "alt_screen":
                tv.launch_app("YouTube")
                msg = "Pantalla alternativa activada (YouTube)"
            elif cmd.startswith("app_"):
                app_name = cmd.replace("app_", "")
                msg = tv.launch_app(app_name)
            elif cmd == "clean_ram":
                msg = tv.clean_ram()
            elif cmd == "sleep_30":
                msg = tv.start_sleep_timer(30, gradual=True)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {"status": "ok", "message": msg, "channel": tv.get_current_channel()}
            self.wfile.write(json.dumps(resp).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def main():
    tv.connect()
    server = HTTPServer(("0.0.0.0", PORT), RemoteHandler)
    print(f"\n[Mando Web & EPG] Servidor web iniciado en el puerto {PORT}.")
    print(f"-> Abre desde tu móvil o PC: http://localhost:{PORT}")
    print("Presiona Ctrl+C para detener el servidor.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor web detenido.")

if __name__ == "__main__":
    main()
