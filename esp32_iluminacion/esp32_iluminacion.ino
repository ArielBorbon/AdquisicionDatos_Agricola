// Librerías
#include <NoDelay.h>
#include <WiFi.h>
#include <MQTT.h> // Requiere instalar la librería "MQTT" de Joel Gaehwiler (256dpi) en el Library Manager
#include "time.h"

// ==========================================
// CONFIGURACIÓN DE RED Y MQTT
// ==========================================
const char* ssid = "hola";
const char* password = "sebas";
const char* mqtt_server = "y ariel";
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
const long PAUSA = 30000; // 30 segundos entre lecturas

// Configuración NTP (Network Time Protocol)
const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = -25200;  // -7*3600 (Hora estándar)
const int daylightOffset_sec = 0;

// Objetos de sistema
WiFiClient espClient;
// Se inicializa el cliente MQTT con un buffer de 256 bytes
MQTTClient client(256);
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
  Serial.println("Iniciando Nodo LDR - Arquitectura por Capas (QoS 1)");
  Serial.println();
  
  // Resolución ADC a 12 bits (0-4095)
  analogReadResolution(12);

  // Configuración del cliente MQTT
  client.begin(mqtt_server, mqtt_port, espClient);
  
  // Configura opciones: keepAlive (30s), cleanSession (false para persistencia), timeout (1000ms)
  client.setOptions(30, false, 1000);
}

void loop() {
  if (conectaRedWiFi() && !client.connected()) {
    reconnect();
  }
  
  if (client.connected()) {
    client.loop(); // Mantiene viva la conexión
  }
  
  if (pausa.update()) {
    actualizaLectura();
  }
}

/*
- Conecta el ESP32 a la red WiFi y sincroniza el reloj interno
*/
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

/*
- Reconecta al Broker MQTT aplicando reglas de ACL y Persistencia
*/
void reconnect() {
  while (!client.connected()) {
    Serial.print("Intentando conexión MQTT con ACL... ");
    
    // Conexión con credenciales. La persistencia (cleanSession = false) 
    // ya se definió en setup() con client.setOptions()
    if (client.connect(client_id, mqtt_user, mqtt_password)) {
      Serial.println("Conectado al broker exitosamente.");
    } else {
      // client.lastError() ayuda a depurar problemas de conexión
      Serial.print("Fallo de conexión. Reintentando en 5 segundos...");
      delay(5000);
    }
  }
}

/*
- Lee los sensores y llama a la función de publicación
*/
void actualizaLectura() {
  obtenFecha(fecha);
  obtenLuminosidad(luminosidad);
  publicaValores();
}

/*
- Obtiene la fecha y hora locales
*/
void obtenFecha(char* pFecha) {
  if (!getLocalTime(&timeinfo)) {
    Serial.println("Error: No se pudo sincronizar NTP");
    pFecha[0] = '\0';
  } else {
    strftime(pFecha, 30, "%d/%m/%Y %H:%M:%S", &timeinfo);
  }
}

/*
- Lee el ADC y lo transforma a porcentaje
*/
void obtenLuminosidad(char* pLuminosidad) {
  int valorCrudo = analogRead(PIN_LDR);
  
  if (isnan(valorCrudo)) {
    Serial.println("Error al leer LDR");
    pLuminosidad[0] = '\0';
  } else {
    float porcentajeLuz = (valorCrudo / 4095.0) * 100.0;
    dtostrf(porcentajeLuz, 6, 2, pLuminosidad);
  }
}

/*
- Publica en el tópico de acuerdo a la capa de percepción
*/
void publicaValores() {
  char mensaje[60];
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, luminosidad);
  
  // Publicación estructurada: publish(topic, payload, retained, qos)
  // retained = true, QoS = 1
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