#include <NoDelay.h>
#include "DHT.h"
#include <WiFi.h>
#include <MQTT.h> // Librería de Joel Gaehwiler (256dpi)
#include "time.h"

const char* ssid = "hola";
const char* password = "sebas";
const char* mqtt_server = "192.168.1.X"; // Poner la IP real de la PC con Mosquitto
const int mqtt_port = 1883;
const char* client_id = "esp32-temperatura-maiz1";

// Credenciales ACL para Mosquitto (Solo escritura)
const char* mqtt_user = "sensor_temp_maiz1";
const char* mqtt_password = "password_seguro_temp";

const char* topicoTemperaturaCent = "campo1/parcelas/maiz1/temperatura/centigrados";
const char* topicoHumedadAire = "campo1/parcelas/maiz1/humedad/aire";

const unsigned int PIN_DHT = 4;
const unsigned int BAUD_RATE = 115200;
const long PAUSA = 30000;

const char* ntpServer = "pool.ntp.org";
const long gmtOffset_sec = -25200; 
const int daylightOffset_sec = 0;

WiFiClient espClient;
MQTTClient client(256);
struct tm timeinfo;
noDelay pausa(PAUSA);
DHT dht(PIN_DHT, DHT11);

char fecha[30];
char temperaturaCent[10];
char humedadAire[10];

bool conectaRedWiFi();
void reconnect();
void actualizaLectura();
void obtenFecha(char* pFecha);
void obtenTempCent(char* pTempCent);
void obtenHumedadAire(char* pHumedad);
void publicaValores();

void setup() {
  Serial.begin(BAUD_RATE);
  delay(100);
  Serial.println("Iniciando Sensor DHT11 - QoS 1 y ACL");
  dht.begin();
  
  client.begin(mqtt_server, mqtt_port, espClient);
  client.setOptions(30, false, 1000); // Persistencia activada
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
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
  }
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);
  return true;
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect(client_id, mqtt_user, mqtt_password)) {
      Serial.println("Conectado a MQTT.");
    } else {
      delay(5000);
    }
  }
}

void actualizaLectura() {
  obtenFecha(fecha);
  obtenTempCent(temperaturaCent);
  obtenHumedadAire(humedadAire);
  publicaValores();
}

void obtenFecha(char* pFecha) {
  if (!getLocalTime(&timeinfo)) {
    pFecha[0] = '\0';
  } else {
    strftime(pFecha, 30, "%d/%m/%Y %H:%M:%S", &timeinfo);
  }
}

void obtenTempCent(char* pTempCent) {
  float tempCent = dht.readTemperature();
  if (isnan(tempCent)) pTempCent[0] = '\0';
  else dtostrf(tempCent, 6, 2, pTempCent);
}

void obtenHumedadAire(char* pHumedad) {
  float humedad = dht.readHumidity();
  if (isnan(humedad)) pHumedad[0] = '\0';
  else dtostrf(humedad, 6, 2, pHumedad);
}

void publicaValores() {
  char mensaje[60];
  
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, temperaturaCent);
  client.publish(topicoTemperaturaCent, mensaje, true, 1);
  
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, humedadAire);
  client.publish(topicoHumedadAire, mensaje, true, 1);
}
