/*
 * Panasonic TV ESP32 Smart Companion
 * Dispositivo autónomo de 4€ para silenciar anuncios y control básico por Wi-Fi.
 */

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>

// ==========================================
// CONFIGURACIÓN DE RED
// ==========================================
const char* WIFI_SSID     = "TU_WIFI";
const char* WIFI_PASSWORD = "TU_PASSWORD";
const char* TV_IP         = "192.168.1.132"; // IP de la TV Panasonic

// Pines
const int PIN_BOTON = 0;           // Botón BOOT integrado en la placa
const int PIN_SENSOR_AUDIO = 34;   // Pin analógico ADC para sensor de sonido (opcional)

// Variables de estado
bool isMuted = false;
unsigned long muteStart = 0;
const unsigned long TIEMPO_ANUNCIOS_MS = 150000; // 2 min y medio

WebServer server(80);

void enviarComandoTV(const char* accion) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    // Si la TV responde en HTTP SOAP o API de control
    String url = "http://" + String(TV_IP) + ":55000/nrc/control_0";
    http.begin(url);
    http.addHeader("Content-Type", "text/xml; charset=\"utf-8\"");
    http.addHeader("SOAPACTION", "\"urn:panasonic-com:service:p00NetworkControl:1#X_SendKey\"");
    
    String body = "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
                  "<s:Envelope xmlns:s=\"http://schemas.xmlsoap.org/soap/envelope/\" s:encodingStyle=\"http://schemas.xmlsoap.org/soap/encoding/\">"
                  "<s:Body><u:X_SendKey xmlns:u=\"urn:panasonic-com:service:p00NetworkControl:1\">"
                  "<X_KeyEvent>NRC_" + String(accion) + "-ONOFF</X_KeyEvent>"
                  "</u:X_SendKey></s:Body></s:Envelope>";
    
    int code = http.POST(body);
    Serial.printf("[ESP32] Comando %s enviado -> HTTP %d\n", accion, code);
    http.end();
  }
}

void toggleMute() {
  enviarComandoTV("MUTE");
  isMuted = !isMuted;
  if (isMuted) {
    muteStart = millis();
    Serial.println("[ESP32] Mute activado con cuenta atrás de 150s.");
  } else {
    muteStart = 0;
    Serial.println("[ESP32] Sonido restaurado.");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BOTON, INPUT_PULLUP);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.printf("\n[ESP32] Conectado. IP: http://%s\n", WiFi.localIP().toString().c_str());

  server.on("/", []() {
    String html = "<html><body style='text-align:center; font-family:sans-serif; background:#111; color:#eee; padding-top:40px;'>"
                  "<h1>ESP32 Mando Panasonic</h1>"
                  "<p>Estado: " + String(isMuted ? "SILENCIADO" : "NORMAL") + "</p>"
                  "<a href='/mute' style='padding:15px 30px; background:#e11d48; color:white; border-radius:10px; text-decoration:none;'>MUTE / ANUNCIOS</a>"
                  "</body></html>";
    server.send(200, "text/html", html);
  });

  server.on("/mute", []() {
    toggleMute();
    server.sendHeader("Location", "/");
    server.send(303);
  });

  server.begin();
}

void loop() {
  server.handleClient();

  // 1. Pulsación de botón físico
  if (digitalRead(PIN_BOTON) == LOW) {
    delay(200);
    toggleMute();
    while (digitalRead(PIN_BOTON) == LOW) { delay(10); }
  }

  // 2. Temporizador para devolver el sonido
  if (isMuted && (millis() - muteStart >= TIEMPO_ANUNCIOS_MS)) {
    Serial.println("[ESP32] Fin de publicidad automático.");
    toggleMute();
  }
}
