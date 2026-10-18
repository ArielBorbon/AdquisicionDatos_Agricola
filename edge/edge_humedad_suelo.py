from edge_meta_data import urlServidor, puerto
import paho.mqtt.client as mqtt
from datetime import datetime

# Id del nodo edge (único)
id_cliente = "edge-humedadSuelo-parcela1"

# Tópico al que se suscribe (viene del ESP32)
topicoHumedadSuelo = ("campo1/parcelas/parcela1/humedad/suelo", 1) # QoS 1

# Tópico que el nodo Edge publica hacia el Dashboard
topicoEdgeHumedadSuelo = "campo1/edge/parcelas/parcela1/humedad/suelo/promedio"

buffer_suelo = []
ventana_actual = None

def obtener_ventana_15_minutos(dt: datetime) -> datetime:
    """Redondea la fecha al bloque de 15 minutos más cercano."""
    minuto_redondeado = (dt.minute // 15) * 15
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

def on_connect(cliente, userdata, flags, rc, properties=None):
    print(f"Conectado al broker MQTT con código {rc}")
    # Suscripción al tópico de humedad de suelo
    cliente.subscribe(topicoHumedadSuelo)

def on_publish(client, userdata, mid, reason_code, properties):
    print("Promedio de humedad de suelo publicado al Dashboard.\n")

def on_message(cliente, userdata, message):
    global buffer_suelo, ventana_actual
    
    payload = message.payload.decode('utf-8')
    topico = message.topic
    
    # Parseo de la cadena asumiendo los primeros 19 caracteres como fecha
    try:
        str_fecha = payload[:19]
        str_valor = payload[19:].strip()
        
        dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
        valor = float(str_valor)
    except ValueError as e:
        print(f"Error de formato en payload: '{payload}'. Error: {e}")
        return

    ventana_mensaje = obtener_ventana_15_minutos(dt_mensaje)
    
    if ventana_actual is None:
        ventana_actual = ventana_mensaje

    # Cierre de ventana y publicación
    if ventana_mensaje > ventana_actual:
        promedio_suelo = sum(buffer_suelo) / len(buffer_suelo) if buffer_suelo else 0.0
        
        print(f"\n--- CIERRE DE VENTANA (SUELO): {ventana_actual.strftime('%H:%M')} ---")
        print(f"Muestras recolectadas: {len(buffer_suelo)}")
        print(f"Promedio de Humedad de Suelo: {promedio_suelo:.2f} %")
        
        # Publicar el promedio hacia el Dashboard con QoS 1
        cliente.publish(topic=topicoEdgeHumedadSuelo, payload=str(round(promedio_suelo, 2)), qos=1)
        
        # Limpiar el búfer
        buffer_suelo.clear()
        ventana_actual = ventana_mensaje

    # Almacenar el valor si corresponde al tópico
    if topico == topicoHumedadSuelo[0]:
        print(f"Lectura Suelo: {str_valor} % - Fecha y hora: {str_fecha}")
        buffer_suelo.append(valor)

# Configuración del cliente MQTT con Sesión Persistente (Clean Session = False)
cliente = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
cliente.on_connect = on_connect
cliente.on_message = on_message
cliente.on_publish = on_publish

# Conexión y ciclo infinito
cliente.connect(host=urlServidor, port=puerto)
cliente.loop_forever()