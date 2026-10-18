#include <NoDelay.h>
#include <WiFi.h>
#include <MQTT.h> // Librería de Joel Gaehwiler (256dpi)
#include "time.h"

// ==========================================
// CONFIGURACIÓN DE RED Y MQTT
// ==========================================
const char* ssid = "hola";
const char* password = "sebas";
const char* mqtt_server = "IP_DEL_SERVIDOR"; // Actualiza esto con la IP de tu broker
const int mqtt_port = 1883;
const char* client_id = "esp32-humedad-parcela1";

// Credenciales ACL para Mosquitto (Solo escritura)
const char* mqtt_user = "sensor_humedad_parc1";
const char* mqtt_password = "password_seguro_humedad";

// ==========================================
// TÓPICOS
// ==========================================
const char* topicoHumedadSuelo = "campo1/parcelas/parcela1/humedad/suelo";

// ==========================================
// PINES Y CONSTANTES
// ==========================================
const unsigned int PIN_FC28 = 35; // Pin analógico ADC
const unsigned int BAUD_RATE = 115200;
const long PAUSA = 30000; // 30 segundos entre lecturas

// Configuración NTP
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = -25200;  // GMT-7 para Sonora
const int daylightOffset_sec = 0;

WiFiClient espClient;
MQTTClient client(256); // Buffer de 256 bytes
struct tm timeinfo;
noDelay pausa(PAUSA);

char fecha[30];
char humedad_suelo[10];

void setup() {
  Serial.begin(BAUD_RATE);
  delay(100);
  Serial.println("Iniciando Sensor FC-28...");
  
  // Resolución ADC a 12 bits (0 a 4095)
  analogReadResolution(12);

  client.begin(mqtt_server, mqtt_port, espClient);
  // Opciones: keepAlive=30s, cleanSession=false (PERSISTENCIA), timeout=1000ms
  client.setOptions(30, false, 1000);
}

void loop() {
  if (conectaRedWiFi() && !client.connected()) {
    reconnect();
  }
  
  if (client.connected()) {
    client.loop(); 
  }
  
  if (pausa.update()) {
    actualizaLectura();
  }
}

bool conectaRedWiFi() {
  if (WiFi.status() == WL_CONNECTED) return true;
  
  WiFi.disconnect(true);
  WiFi.begin(ssid, password);
  Serial.print("Conectando a WiFi...");

  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  
  Serial.println("\nWiFi conectado.");
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  return true;
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Conectando a MQTT... ");
    if (client.connect(client_id, mqtt_user, mqtt_password)) {
      Serial.println("Conectado.");
    } else {
      Serial.println("Fallo. Reintentando en 5s...");
      delay(5000);
    }
  }
}

void actualizaLectura() {
  obtenFecha(fecha);
  obtenHumedad(humedad_suelo);
  publicaValores();
}

void obtenFecha(char* pFecha) {
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Error de sincronización NTP");
    pFecha[0] = '\0';
  } else {
    strftime(pFecha, 30, "%d/%m/%Y %H:%M:%S", &timeinfo);
  }
}

void obtenHumedad(char* pHumedad) {
  int valorCrudo = analogRead(PIN_FC28);
  
  // 4095 = 0% (Seco) | 0 = 100% (Mojado)
  float porcentajeHumedad = (1.0 - (valorCrudo / 4095.0)) * 100.0;
  
  // Restringir márgenes de error analógicos
  if (porcentajeHumedad < 0) porcentajeHumedad = 0;
  if (porcentajeHumedad > 100) porcentajeHumedad = 100;
  
  dtostrf(porcentajeHumedad, 6, 2, pHumedad);
}

void publicaValores() {
  char mensaje[60];
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, humedad_suelo);
  
  // Enviar mensaje con Retained = true, QoS = 1
  bool exito = client.publish(topicoHumedadSuelo, mensaje, true, 1);
  
  Serial.print("Publicando -> Topico: ");
  Serial.print(topicoHumedadSuelo);
  Serial.print(" | Mensaje: ");
  Serial.print(mensaje);
  
  if(exito){
    Serial.println(" [OK - QoS 1]");
  } else {
    Serial.println(" [ERROR]");
  }
}