// Librerías
#include <NoDelay.h>
#include <WiFi.h>
#include <MQTT.h> 
#include "time.h"

// ==========================================
// CONFIGURACIÓN DE RED Y MQTT
// ==========================================
const char* ssid = "INFINITUM41HI";
const char* password = "dmP683Yu4S26";
const char* mqtt_server = "192.168.1.85";
const int mqtt_port = 1883;
const char* client_id = "esp32-luminosidad-invernadero1";

// ==========================================
// CREDENCIALES ACL (Access Control List)
// ==========================================
const char* mqtt_user = "sensor_ldr_inv1";
const char* mqtt_password = "password_seguro_ldr";

// ==========================================
// TÓPICOS
// ==========================================
const char* topicoLuminosidad = "campo1/invernaderos/invernadero1/luminosidad";

// ==========================================
// PINES Y CONSTANTES
// ==========================================
const unsigned int PIN_LDR = 34; // Pin analógico ADC1
const unsigned int BAUD_RATE = 115200;
const long PAUSA = 2000; // REDUCIDO A 2 SEGUNDOS PARA EL CARRIL RÁPIDO

// Configuración NTP (Network Time Protocol)
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = -25200;  // -7*3600 (Hora estándar)
const int daylightOffset_sec = 0;

// Objetos de sistema
WiFiClient espClient;
MQTTClient client(512); // Buffer ampliado a 512 bytes para mayor tolerancia
struct tm timeinfo;
noDelay pausa(PAUSA);

// Variables de almacenamiento
char fecha[30];
char luminosidad[10];

// Declaración de funciones
bool conectaRedWiFi();
void reconnect();
void actualizaLectura();
void obtenFecha(char* pFecha);
void obtenLuminosidad(char* pLuminosidad);
void publicaValores();

void setup() {
  Serial.begin(BAUD_RATE);
  delay(100);
  Serial.println("Iniciando Nodo LDR - Fast Track (QoS 1)");
  Serial.println();
  
  analogReadResolution(12);

  client.begin(mqtt_server, mqtt_port, espClient);
  client.setOptions(30, false, 5000); // Timeout ampliado a 5s
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
  Serial.print("Conectando a WiFi: ");
  Serial.print(ssid);

  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  
  Serial.println("\nConexión WiFi establecida.");
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);

  return true;
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Intentando conexión MQTT con ACL... ");
    
    if (client.connect(client_id, mqtt_user, mqtt_password)) {
      Serial.println("Conectado al broker exitosamente.");
    } else {
      Serial.print("Fallo de conexión. Reintentando en 5 segundos...");
      delay(5000);
    }
  }
}

void actualizaLectura() {
  obtenFecha(fecha);
  obtenLuminosidad(luminosidad);
  publicaValores();
}

void obtenFecha(char* pFecha) {
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Error: No se pudo sincronizar NTP");
    pFecha[0] = '\0';
  } else {
    strftime(pFecha, 30, "%d/%m/%Y %H:%M:%S", &timeinfo);
  }
}

void obtenLuminosidad(char* pLuminosidad) {
  int valorCrudo = analogRead(PIN_LDR);
  
  if (isnan(valorCrudo)) {
    Serial.println("Error al leer LDR");
    pLuminosidad[0] = '\0';
  } else {
    // CORRECCIÓN: Se agregó el operador de multiplicación faltante (*)
    float porcentajeLuz = (valorCrudo / 4095.0) * 100.0;
    dtostrf(porcentajeLuz, 6, 2, pLuminosidad);
  }
}

void publicaValores() {
  char mensaje[60];
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, luminosidad);
  
  bool exito = client.publish(topicoLuminosidad, mensaje, true, 1);
  
  Serial.print("ACL/QoS -> Topico: ");
  Serial.print(topicoLuminosidad);
  Serial.print(" | Msj: ");
  Serial.print(mensaje);
  
  if(exito){
    Serial.println(" [ENVIADO - QoS 1 Confirmado]");
  } else {
    Serial.println(" [ERROR AL ENVIAR]");
  }
}