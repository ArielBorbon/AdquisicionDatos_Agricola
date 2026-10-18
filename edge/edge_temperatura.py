from edge_meta_data import urlServidor
from edge_meta_data import puerto
import temperatura_metricas
import paho.mqtt.client as mqtt
import sys
from datetime import datetime

# Id del nodo edge de la temperatura
id_cliente = "edge-temperatura-parcela-maiz1"

# Tópicos a los que se suscribe el nodo Edge automáticamente
topicoTemperaturaCentigrados = ("campo1/parcela/maiz1/temperatura/centigrados", 1) # Topico - QoS
topicoHumedad = ("campo1/parcela/maiz1/humedad", 1)
# Tópicos que el nodo Edge publica al Dashboard
topicoEdgeTemperaturaCentigrados = ("campo1/edge/parcela/maiz1/temperatura/centigrados/promedio", 1)
topicoEdgeHumedad = ("campo1/edge/parcela/maiz1/humedad/promedio", 1)
topicoEdgeDpv = ("campo1/edge/parcela/maiz1/dpv", 1)
topicoEdgeDpd = ("campo1/edge/parcela/maiz1/dpd", 1)
topicoEdgeGdd = ("campo1/edge/parcela/maiz1/gdd", 1)

buffer_temp = []
buffer_hum = []
ventana_actual = None

def obtener_ventana_15_minutos(dt: datetime) -> datetime:
    """
        Toma un datetime y lo redondea hacia abajo al bloque de 15 minutos más cercano.
        Ej: 12:24:01 -> 12:15:00
        Ej: 12:31:45 -> 12:30:00
    """
    minuto_redondeado = (dt.minute // 15) * 15
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

# Funcion invocada cuando se establece la conexion con el
# servidor MQTT
def on_connect(cliente, userdata, flags, rc, properties=None):
    print(f"Conectado con el codigo {rc}")
    # El cliente se subscribe al topico en el servidor MQTT
    cliente.subscribe(topicoTemperaturaCentigrados)
    cliente.subscribe(topicoHumedad)

# Funcion invocada cuando se publica un mensaje al servidor MQTT
def on_publish(client, userdata, mid, reason_code, properties):
    print("Se publicaron los datos\n")

# Funcion invocada cuando se recibe un mensaje del servidor MQTT
def on_message(cliente, userdata, message):
    
    global buffer_temp, buffer_hum, ventana_actual
    
    payload = message.payload.decode('utf-8')
    topico = message.topic
    
    # 1. Parseo seguro de la cadena (Basado en longitud fija)
    # Formato esperado: "18/03/2023 12:24:01  29.00"
    # Los primeros 19 caracteres siempre son la fecha, el resto es el valor.
    try:
        str_fecha = payload[:19]
        str_valor = payload[19:].strip()
        
        dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
        valor = float(str_valor)
    
    except ValueError as e:
        print(f"Error de formato en payload: '{payload}'. Error: {e}")
        return

    # 2. Determinar a qué bloque de 15 minutos pertenece este mensaje
    ventana_mensaje = obtener_ventana_15_minutos(dt_mensaje)
    
    # Inicializar la primera ventana al recibir el primer mensaje
    if ventana_actual is None:
        ventana_actual = ventana_mensaje

    # 3. Lógica de Cierre de Ventana
    # Si la fecha de este mensaje es MAYOR a la ventana actual, el bloque de 15 min terminó.
    if ventana_mensaje > ventana_actual:
        
        # Calcular los promedios evitando división por cero
        promedio_temp = sum(buffer_temp) / len(buffer_temp) if buffer_temp else 0.0
        promedio_hum = sum(buffer_hum) / len(buffer_hum) if buffer_hum else 0.0
        
        print(f"\n--- CIERRE DE VENTANA: {ventana_actual.strftime('%H:%M')} ---")
        print(f"Muestras de Temp: {len(buffer_temp)} | Muestras de Hum: {len(buffer_hum)}")
        print(f"Promedio Temperatura: {promedio_temp:.2f} °C")
        print(f"Promedio Humedad: {promedio_hum:.2f} %")
        
        # Se obtiene el dpv
        dpv = temperatura_metricas.calcular_dpv(promedio_temp, promedio_hum)
        dpd = temperatura_metricas.calcular_dpd(promedio_temp, promedio_hum)
        print(f"DPV: {dpv} °C")
        print(f"DPD: {dpd} °C")
        
        # Se publican los datos
        # cliente.publish(topic = topicoEdgeTemperaturaCentigrados, payload = str(promedio_temp))
        # cliente.publish(topic = topicoEdgeHumedad, payload = str(promedio_hum))
        # cliente.publish(topic = topicoEdgeDpv, payload = str(dpv))
        # cliente.publish(topic = topicoEdgeDpd, payload = str(dpd))
        
        # Limpiar los arreglos y actualizar la ventana a la nueva
        buffer_temp.clear()
        buffer_hum.clear()
        ventana_actual = ventana_mensaje

    # 4. Almacenar el valor actual en el buffer correspondiente
    if topico == topicoTemperaturaCentigrados[0]:
        print(f"Temperatura: {str_valor} °C - Fecha y hora: {str_fecha}")
        buffer_temp.append(valor)
    elif topico == topicoHumedad[0]:
        print(f"Humedad: {str_valor} % - Fecha y hora: {str_fecha}")
        buffer_hum.append(valor)

# Crea una instancia de la clase Client
cliente = mqtt.Client(client_id = id_cliente, callback_api_version = mqtt.CallbackAPIVersion.VERSION2)
cliente.on_connect = on_connect
cliente.on_message = on_message
cliente.on_publish = on_publish

# Establece una conexion con el servidor MQTT
cliente.connect(host = urlServidor, port = puerto)

# Se mantiene en un ciclo de espera de los mensajes del servidor
cliente.loop_forever()