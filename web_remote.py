#!/usr/bin/env python3
"""
Panasonic Google TV Web Remote
Servidor web ligero para controlar la TV desde el móvil en la misma red Wi-Fi.
Puerto por defecto: 8080. Sin dependencias externas.
"""

import sys
import os
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Importar gestor
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "core")))
from tv_manager import PanasonicTVManager

TV_IP = os.getenv("TV_IP", "192.168.1.132:5555")
PORT = int(os.getenv("WEB_PORT", "8080"))
tv = PanasonicTVManager(tv_ip=TV_IP)

HTML_PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Mando TV Panasonic</title>
    <style>
        :root {
            --bg: #0f172a;
            --card: #1e293b;
            --primary: #3b82f6;
            --accent: #ef4444;
            --text: #f8fafc;
            --text-dim: #94a3b8;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            width: 100%;
            max-width: 420px;
        }
        header {
            text-align: center;
            margin-bottom: 20px;
        }
        h1 { margin: 0; font-size: 22px; }
        .channel-badge {
            display: inline-block;
            margin-top: 6px;
            padding: 4px 12px;
            background: var(--card);
            border-radius: 12px;
            font-size: 13px;
            color: #38bdf8;
        }
        .btn-publi {
            width: 100%;
            padding: 18px;
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
            border: none;
            border-radius: 16px;
            font-size: 18px;
            font-weight: bold;
            box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);
            margin-bottom: 20px;
            cursor: pointer;
            transition: transform 0.1s;
        }
        .btn-publi:active { transform: scale(0.98); }
        .card {
            background: var(--card);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .grid-3 {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }
        .grid-2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        button.btn {
            background: #334155;
            color: white;
            border: none;
            padding: 14px;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 500;
            cursor: pointer;
        }
        button.btn:active { background: #475569; }
        .dpad {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            grid-template-rows: repeat(3, 1fr);
            gap: 10px;
            margin: 10px auto;
            max-width: 240px;
        }
        .dpad-center {
            background: var(--primary) !important;
            font-weight: bold;
        }
        .app-btn {
            background: #1e1b4b !important;
            border: 1px solid #4338ca !important;
            color: #c7d2fe !important;
            font-size: 13px !important;
            padding: 12px !important;
        }
        #toast {
            position: fixed;
            bottom: 20px;
            background: #10b981;
            color: white;
            padding: 10px 20px;
            border-radius: 20px;
            display: none;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Panasonic Smart Hub</h1>
            <div class="channel-badge" id="canal">Conectando...</div>
        </header>

        <button class="btn-publi" onclick="sendAction('publi')">
            🔇 MODO PUBLICIDAD (150s)
        </button>

        <div class="card">
            <div class="grid-3">
                <button class="btn" onclick="sendAction('vol_down')">Vol -</button>
                <button class="btn" onclick="sendAction('mute')">Mute</button>
                <button class="btn" onclick="sendAction('vol_up')">Vol +</button>
            </div>
        </div>

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
            <div class="grid-3" style="margin-top:10px;">
                <button class="btn" onclick="sendAction('back')">↩ Volver</button>
                <button class="btn" onclick="sendAction('home')">⌂ Home</button>
                <button class="btn" onclick="sendAction('power')" style="background:#7f1d1d;">⏻ Apagar</button>
            </div>
        </div>

        <div class="card">
            <div style="font-size:14px; margin-bottom:10px; color:var(--text-dim);">Lanzar App</div>
            <div class="grid-2">
                <button class="btn app-btn" onclick="sendAction('app_YouTube')">YouTube</button>
                <button class="btn app-btn" onclick="sendAction('app_Netflix')">Netflix</button>
                <button class="btn app-btn" onclick="sendAction('app_Movistar+')">Movistar+</button>
                <button class="btn app-btn" onclick="sendAction('app_TDT Live TV')">TDT Directo</button>
            </div>
        </div>

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
                    if (data.channel) document.getElementById('canal').innerText = data.channel;
                })
                .catch(() => showToast('Error de conexión'));
        }

        function showToast(msg) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.style.display = 'block';
            setTimeout(() => { t.style.display = 'none'; }, 2000);
        }

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
        if url.path == "/" or url.path == "/index.html":
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
        elif url.path == "/api/action":
            qs = urllib.parse.parse_qs(url.query)
            cmd = qs.get("cmd", [""])[0]
            msg = "Comando desconocido"
            
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
                tv.start_sleep_timer(2.5, gradual=False) # Modo publicidad 150s
                msg = "Modo Publicidad activado (150s)"
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
    print(f"\n[Mando Web] Servidor web iniciado en el puerto {PORT}.")
    print(f"-> Abre desde tu móvil o PC: http://localhost:{PORT}")
    print("Presiona Ctrl+C para detener el servidor.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor web detenido.")

if __name__ == "__main__":
    main()
