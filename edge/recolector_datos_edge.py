import paho.mqtt.client as mqtt
from datetime import datetime
import temperatura_metricas
from edge_meta_data import urlServidor, puerto

id_cliente = "edge-gateway-principal"
mqtt_user = "edge_node"
mqtt_password = "password_seguro_edge"

TOPICOS_ENTRADA = [
    ("campo1/parcelas/maiz1/temperatura/centigrados", 1),
    ("campo1/parcelas/maiz1/humedad/aire", 1),
    ("campo1/parcelas/parcela1/humedad/suelo", 1),
    ("campo1/invernaderos/invernadero1/luminosidad", 1)
]

TOPICOS_SALIDA = {
    "temp_prom": "campo1/edge/parcelas/maiz1/temperatura/promedio",
    "hum_aire_prom": "campo1/edge/parcelas/maiz1/humedad_aire/promedio",
    "dpv": "campo1/edge/parcelas/maiz1/dpv",
    "dpd": "campo1/edge/parcelas/maiz1/dpd",
    "hum_suelo_prom": "campo1/edge/parcelas/parcela1/humedad_suelo/promedio",
    "lum_prom": "campo1/edge/invernaderos/invernadero1/luminosidad/promedio",
    # NUEVO TÓPICO PARA EL ESTADO (SEMÁFORO)
    "lum_estado": "campo1/edge/invernaderos/invernadero1/luminosidad/estado"
}

buffers = {
    "campo1/parcelas/maiz1/temperatura/centigrados": [],
    "campo1/parcelas/maiz1/humedad/aire": [],
    "campo1/parcelas/parcela1/humedad/suelo": [],
    "campo1/invernaderos/invernadero1/luminosidad": []
}
ventana_actual = None

def obtener_ventana_15_minutos(dt: datetime) -> datetime:
    minuto_redondeado = (dt.minute // 15) * 15
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

def calcular_promedio(lista):
    return sum(lista) / len(lista) if lista else 0.0

def on_connect(cliente, userdata, flags, reason_code, properties=None):
    print(f"Edge conectado al broker MQTT con código {reason_code}")
    cliente.subscribe(TOPICOS_ENTRADA)

def on_message(cliente, userdata, message):
    global buffers, ventana_actual
    payload = message.payload.decode('utf-8')
    topico = message.topic
    
    try:
        str_fecha = payload[:19]
        str_valor = payload[19:].strip()
        dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
        valor = float(str_valor)
    except ValueError as e:
        return

    ventana_mensaje = obtener_ventana_15_minutos(dt_mensaje)
    if ventana_actual is None:
        ventana_actual = ventana_mensaje

    if ventana_mensaje > ventana_actual:
        procesar_y_publicar_ventana(cliente, ventana_actual)
        ventana_actual = ventana_mensaje

    if topico in buffers:
        buffers[topico].append(valor)

def procesar_y_publicar_ventana(cliente, ventana):
    global buffers
    print(f"\n--- CIERRE DE VENTANA EDGE: {ventana.strftime('%H:%M')} ---")
    
    prom_temp = calcular_promedio(buffers["campo1/parcelas/maiz1/temperatura/centigrados"])
    prom_hum_aire = calcular_promedio(buffers["campo1/parcelas/maiz1/humedad/aire"])
    prom_hum_suelo = calcular_promedio(buffers["campo1/parcelas/parcela1/humedad/suelo"])
    prom_lum = calcular_promedio(buffers["campo1/invernaderos/invernadero1/luminosidad"])
    
    if prom_temp > 0 and prom_hum_aire > 0:
        dpv = temperatura_metricas.calcular_dpv(prom_temp, prom_hum_aire)
        dpd = temperatura_metricas.calcular_dpd(prom_temp, prom_hum_aire)
    else:
        dpv = dpd = 0.0

    # EVALUACIÓN DEL ESTADO LUMÍNICO (SEMÁFORO)
    if prom_lum <= 20:
        estado_lum = "Gris|Fotosíntesis mínima o nula.|Condición normal de noche. Si ocurre de día, encender iluminación artificial o revisar obstrucciones."
    elif prom_lum <= 50:
        estado_lum = "Azul|Adecuado para plantas de sombra, pero insuficiente para maximizar el rendimiento de maíz/tomate.|Retirar mallas sombra si están desplegadas."
    elif prom_lum <= 85:
        estado_lum = "Verde|Rango ideal. Tasa de asimilación fotosintética máxima sin generar estrés térmico.|Condiciones ideales, no se requiere acción."
    else:
        estado_lum = "Rojo|Radiación extrema. Alto riesgo de fotoinhibición y quemaduras en el tejido vegetal.|Precaución. Desplegar malla sombra al 30% o 50% inmediatamente."

    cliente.publish(TOPICOS_SALIDA["temp_prom"], str(round(prom_temp, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_aire_prom"], str(round(prom_hum_aire, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpv"], str(dpv), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpd"], str(dpd), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_suelo_prom"], str(round(prom_hum_suelo, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["lum_prom"], str(round(prom_lum, 2)), qos=1)
    
    # PUBLICACIÓN DEL ESTADO (SEPARADO POR '|')
    cliente.publish(TOPICOS_SALIDA["lum_estado"], estado_lum, qos=1)
    
    for key in buffers:
        buffers[key].clear()

cliente = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
cliente.username_pw_set(username=mqtt_user, password=mqtt_password)
cliente.on_connect = on_connect
cliente.on_message = on_message
cliente.connect(host=urlServidor, port=puerto)
cliente.loop_forever()