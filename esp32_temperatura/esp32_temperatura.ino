// Librerías
#include <NoDelay.h>
#include "DHT.h"
#include <WiFi.h>
#include <PubSubClient.h>
#include "time.h"

// Nombre del SSID de la red Wi-Fi a conectarse
const char* ssid = "hola";
// Contraseña para la red Wi-Fi
const char* password = "sebas";
// URL del servidor MQTT
const char* mqtt_server = "y ariel";
// Puerto del broker MQTT
const int mqtt_port = 1883;
// Id del cliente
const char* client_id = "esp32-temperatura-cafe1";

// Tópicos de la temperatura
const char* topicoTemperaturaCent = "campo1/invernadero/cafe1/temperatura/centigrados";
const char* topicoTemperaturaFahr = "campo1/invernadero/cafe1/temperatura/fahrenheit";
const char* topicoTemperaturaCent = "campo1/parcela/maiz1/temperatura/centigrados";

// Pin a la que esta conectado el sensor DHT11, GPIO4
const unsigned int PIN_DHT = 4;
// Velocidad de transmisión del puerto serie
const unsigned int BAUD_RATE = 115200;
// Tiempo entre lecturas del sensor DHT11
const long PAUSA = 30000; // 30 segundos ya que el clima no cambia con tanta frecuencia

// URL de un servidor NTP (Network Time Protocol)
const char* ntpServer = "pool.ntp.org";
// Offset en segundos de la zona horaria local con respecto a GMT
const long gmtOffset_sec = -25200;  // -7*3600
// Offset en segundos del tiempo, en el caso de horario de verano
const int daylightOffset_sec = 0;

// Cliente WiFi
WiFiClient espClient;
// Cliente MQTT
PubSubClient client(espClient);

// Estructura con la informacion de la fecha/hora actual
struct tm timeinfo;
// Crea una instancia de la clase noDelay
// que determina si han transcurrido PERIODO ms
noDelay pausa(PAUSA);
// Crea una instancia de la clase DHT11
DHT dht(PIN_DHT, DHT11);

// Variable con la fecha y hora del sistema
char fecha[30];
// Variable con el valor de la temperatura en grados centígrados
char temperaturaCent[10];
// Variable con el valor de la humedad
char humedad[10];

bool conectaRedWiFi();
void reconnect();
void obtenFecha(char* pFecha);
void obtenTempCent(char* pTempCent);
void obtenHumedad(char* pHumedad);
void publicaValores();

void setup() {
  // Establece la velocidad de transmisión del puerto
  // serie al valor BAUD_RATE
  Serial.begin(BAUD_RATE);
  delay(100);
  Serial.println("Prueba del sensor DHT11");
  // Inicializa el sensor DHT11
  dht.begin();
  Serial.println();
  // Establece el URL y puerto del servidor MQTT
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  // Si el cliente no esta conectado al servidor MQTT
  if (conectaRedWiFi() && !client.connected()) {
    // Establece la conexion con el servidor MQTT
    reconnect();
  }
  // Creo que esto nos será útil después (QoS, mensajes ACK)
  if (client.connected()) {
    client.loop();
  }
  // Verifica si es tiempo de leer el sensor DHT11
  if (pausa.update()) {
    // Lee el sensor y publica la humedad y temperatura
    // al servidor MQTT
    actualizaLectura();
  }
}

/*
* Conecta el microcontrolador ESP32 a una red WiFi
*/
bool conectaRedWiFi() {
  // Verifica si la conexión ya está establecida
  if (WiFi.status() == WL_CONNECTED) return true;
  
  // En caso contrario, se conecta a la red
  WiFi.disconnect(true);
  WiFi.begin(ssid, password);
  Serial.print("Conectandose a la red ");
  Serial.print(ssid);
  Serial.println(" ...");

  // Mientras no se ha conectado a la red WiFi
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  
  Serial.println('\n');
  Serial.println("Connexion establecida");

  // Inicializa el cliente NTP, obtiene la fecha/hora del
  // servidor NTP e inicializa el reloj interno del
  // microcontrolador ESP32
  configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);

  // Regresa verdadero después de configurar la conexión
  return true;
}

/*
* Reconecta al ESP32 al servidor MQTT en caso de desconexion
*/
void reconnect() {
  // Mientras el ESP32 siga desconectado
  while (!client.connected()) {
    // Si no se conecta
    if (!client.connect(client_id)) {
      // Hace una pausa antes de reintentar conectarse
      delay(5000);
    }
  }
}

/**
* Esta funcion lee del sensor DHT11, la humedad y temperatura
* y las publica al servidor MQTT
*/
void actualizaLectura() {
  // lee la fecha y hora del sistema
  obtenFecha(fecha);
  // Lee el valor de la temperatura en grados centígrados
  obtenTempCent(temperaturaCent);
  // Lee el valor de la humedad
  obtenHumedad(humedad);
  // Publica a humedad y temperatura al servidor MQTT
  publicaValores();
}

/*
* Esta funcion obtiene la fecha y hora locales del sistema
*/
void obtenFecha(char* pFecha) {
  // Obtiene la fecha y hora actual
  if (!getLocalTime(&timeinfo)) {
    Serial.println("No se pudo obtener la fecha/hora");
    pFecha[0] = '\0';
  } else {
    strftime(pFecha, 30, "%d/%m/%Y %H:%M:%S", &timeinfo);
  }
}

/*
* Esta funcion lee la temperatura en grados centigrados usando
* el sensor DHT11. Toma alrededor de 250 ms
*/
void obtenTempCent(char* pTempCent) {
  // Lee la temperatura en grados centigrados
  float tempCent = dht.readTemperature();
  // Verifica que la lectura sea correcta
  if (isnan(tempCent)) {
    Serial.println("Error al leer el sensor DHT11");
    pTempCent[0] = '\0';
  } else
    dtostrf(tempCent, 6, 2, pTempCent);
}

/*
* Esta funcion lee la humedad usando el sensor DHT11.
* Toma alrededor de 250 ms
*/
void obtenHumedad(char* pHumedad) {
  // Lee la humedad
  float humedad = dht.readHumidity();
  // Verifica que la lectura sea correcta
  if (isnan(humedad)) {
    Serial.println("Error al leer el sensor DHT11");
    pHumedad[0] = '\0';
  } else
    dtostrf(humedad, 6, 2, pHumedad);
}

/*
* Esta funcion publica al servidor MQTT
* las lecturas obtenidas del sensor DHT11
*/
void publicaValores() {
  char mensaje[60];
  // Crea mensaje con la temperatura en grados
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, temperaturaCent); // Publica únicamente el valor
  // Publica la temperatura en grados centigrados
  client.publish(topicoTemperaturaCent, mensaje, true);
  // Crea mensaje con la humedad
  strcpy(mensaje, fecha);
  strcat(mensaje, " ");
  strcat(mensaje, humedad); // Publica únicamente el valor
  // Publica la humedad
  client.publish(topicoHumedad, mensaje, true);
}
