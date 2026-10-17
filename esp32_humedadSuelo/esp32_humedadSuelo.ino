// Librerías
#include <NoDelay.h>
#include <WiFi.h>
#include <MQTT.h> // Librería "MQTT" de Joel Gaehwiler (256dpi)
#include "time.h"

// ==========================================
// CONFIGURACIÓN DE RED Y MQTT
// ==========================================
const char* ssid = "hola";
const char* password = "sebas";
const char* mqtt_server = "y ariel";
const int mqtt_port = 1883;
const char* client_id = "esp32-humedad-parcela1";

// ==========================================
// CREDENCIALES ACL (Access Control List)
// ==========================================
// Credenciales para Mosquitto con permisos de solo escritura (write)
const char* mqtt_user = "sensor_humedad_parc1";
const char* mqtt_password = "password_seguro_humedad";

// ==========================================
// TÓPICOS
// ==========================================
const char* topicoHumedad = "campo1/parcelas/parcela1/humedad/suelo";

// ==========================================
// PINES Y CONSTANTES
// ==========================================
// Pin analógico ADC1 para el sensor FC-28 (Ej. GPIO35)
const unsigned int PIN_FC28 = 35; 
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
char humedad[10];

// Declaración de funciones
bool conectaRedWiFi();
void reconnect();
void actualizaLectura();
void obtenFecha(char* pFecha);
void obtenHumedad(char* pHumedad);
void publicaValores();

void setup() {
  Serial.begin(BAUD_RATE);
  delay(100);
  Serial.println("Iniciando Nodo Humedad de Suelo (FC-28) - Arquitectura por Capas (QoS 1)");
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
    
    // Conexión con credenciales (cleanSession = false ya está en setup)
    if (client.connect(client_id, mqtt_user, mqtt_password)) {
      Serial.println("Conectado al broker exitosamente.");
    } else {
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
  obtenHumedad(humedad);
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
- Lee el ADC analógico del higrómetro y lo transforma a porcentaje
*/
void obtenHumedad(char* pHumedad) {
  int valorCrudo = analogRead(PIN_FC28);
  
  if (isnan(valorCrudo)) {
    Serial.println("Error al leer Higrómetro FC-28");
    pHumedad[0] = '\0';
  } else {
    // NOTA TÉCNICA: En los sensores FC-28 analógicos, la resistencia disminuye 
    // cuando hay más humedad. Por lo tanto, un valor cercano a 4095 significa SECO (0%) 
    // y un valor cercano a 0 significa MOJADO (100%).
    // Se invierte la fórmula para obtener un porcentaje real:
    float porcentajeHumedad = (1.0 - (valorCrudo / 4095.0)) * 100.0;
    
    // Si la humedad calculada sale negativa por variaciones del sensor, limitarla a 0
    if (porcentajeHumedad < 0) porcentajeHumedad = 0;
    
    dtostrf(porcentajeHumedad, 6, 2, pHumedad);
  }
}

/*
- Publica en el tópico de acuerdo a la capa de percepción
*/
void publicaValores() {
  char mensaje[60];
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, humedad);
  
  // Publicación estructurada: publish(topic, payload, retained, qos)
  // retained = true, QoS = 1
  bool exito = client.publish(topicoHumedad, mensaje, true, 1);
  
  Serial.print("ACL/QoS -> Topico: ");
  Serial.print(topicoHumedad);
  Serial.print(" | Msj: ");
  Serial.print(mensaje);
  
  if(exito){
    Serial.println(" [ENVIADO - QoS 1 Confirmado]");
  } else {
    Serial.println(" [ERROR AL ENVIAR]");
  }
}