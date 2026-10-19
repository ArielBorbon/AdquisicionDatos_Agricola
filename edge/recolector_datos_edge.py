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
    "gdd": "campo1/edge/parcelas/maiz1/gdd", 
    "hum_suelo_prom": "campo1/edge/parcelas/parcela1/humedad_suelo/promedio",
    "hum_suelo_estado": "campo1/edge/parcelas/parcela1/humedad_suelo/estado",
    "tasa_secado": "campo1/edge/parcelas/parcela1/humedad_suelo/tasa_secado", 
    "lum_prom": "campo1/edge/invernaderos/invernadero1/luminosidad/promedio",
    "lum_estado": "campo1/edge/invernaderos/invernadero1/luminosidad/estado"
}

# Se retira la luminosidad del buffer para no generar promedios retrasados
buffers = {
    "campo1/parcelas/maiz1/temperatura/centigrados": [],
    "campo1/parcelas/maiz1/humedad/aire": [],
    "campo1/parcelas/parcela1/humedad/suelo": []
}
ventana_actual = None

# Variables para metricas acumulativas y comparativas
gdd_acumulado = 0.0 # GDD de la temporada
ultimo_promedio_suelo = None
ultima_hora_secado = None

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

    # =======================================================
    # CARRIL RÁPIDO (FAST-TRACK) PARA LUMINOSIDAD (DEMO EN VIVO)
    # =======================================================
    if topico == "campo1/invernaderos/invernadero1/luminosidad":
        # Evaluar el semáforo y publicar instantáneamente
        if valor <= 20:
            estado_lum = "Gris|Fotosíntesis mínima o nula.|Condición normal de noche. Si ocurre de día, encender iluminación artificial o revisar obstrucciones."
        elif valor <= 50:
            estado_lum = "Azul|Adecuado para plantas de sombra, pero insuficiente para maximizar el rendimiento de maíz/tomate.|Retirar mallas sombra si están desplegadas."
        elif valor <= 85:
            estado_lum = "Verde|Rango ideal. Tasa de asimilación fotosintética máxima sin generar estrés térmico.|Condiciones ideales, no se requiere acción."
        else:
            estado_lum = "Rojo|Radiación extrema. Alto riesgo de fotoinhibición y quemaduras en el tejido vegetal.|Precaución. Desplegar malla sombra al 30% o 50% inmediatamente."

        cliente.publish(TOPICOS_SALIDA["lum_prom"], str(round(valor, 2)), qos=1)
        cliente.publish(TOPICOS_SALIDA["lum_estado"], estado_lum, qos=1)
        print(f"[FAST-TRACK] Luminosidad reenviada: {valor}% -> {estado_lum.split('|')[0]}")
        
        # Salimos de la función para que no pase a la lógica de bloques de 15 min
        return

    # =======================================================
    # LÓGICA DE VENTANAS (15 MIN) PARA TEMPERATURA Y SUELO
    # =======================================================
    ventana_mensaje = obtener_ventana_15_minutos(dt_mensaje)
    if ventana_actual is None:
        ventana_actual = ventana_mensaje

    if ventana_mensaje > ventana_actual:
        procesar_y_publicar_ventana(cliente, ventana_actual, dt_mensaje) 
        ventana_actual = ventana_mensaje

    if topico in buffers:
        buffers[topico].append(valor)

def procesar_y_publicar_ventana(cliente, ventana, dt_actual):
    global buffers, gdd_acumulado, ultimo_promedio_suelo, ultima_hora_secado
    print(f"\n--- CIERRE DE VENTANA EDGE: {ventana.strftime('%H:%M')} ---")
    
    prom_temp = calcular_promedio(buffers["campo1/parcelas/maiz1/temperatura/centigrados"])
    prom_hum_aire = calcular_promedio(buffers["campo1/parcelas/maiz1/humedad/aire"])
    prom_hum_suelo = calcular_promedio(buffers["campo1/parcelas/parcela1/humedad/suelo"])
    
    # 1. Metricas Ambientales (DPV, DPD)
    if prom_temp > 0 and prom_hum_aire > 0:
        dpv = temperatura_metricas.calcular_dpv(prom_temp, prom_hum_aire)
        dpd = temperatura_metricas.calcular_dpd(prom_temp, prom_hum_aire)
    else:
        dpv = dpd = 0.0

    # 2. Dias Grados de Cultivo (GDD) - Maiz (Tb = 10C)
    gdh = prom_temp - 10.0
    if gdh < 0: gdh = 0 # No hay crecimiento si Th < Tb
    gdd_ventana = gdh / (24 * 4) # cuatro ventanas de 15 min en una hora
    gdd_acumulado += gdd_ventana
    
    # 3. Estado de Saturacion Hidrica (Semaforo de Riego)
    if prom_hum_suelo >= 80:
        estado_suelo = "Azul|Suelo saturado y sin oxígeno.|Peligro de pudrición de raíces; no regar."
    elif prom_hum_suelo >= 50:
        estado_suelo = "Verde|Rango óptimo donde la planta absorbe agua sin esfuerzo.|Capacidad de Campo. Condiciones ideales."
    elif prom_hum_suelo >= 30:
        estado_suelo = "Amarillo|El suelo se está secando y el agua se retiene con más fuerza.|Estrés Leve. Monitorear para próximo riego."
    else:
        estado_suelo = "Rojo|Condición crítica. La planta no tiene fuerza de succión.|Punto de Marchitez. Regar inmediatamente."

    # 4. Tasa de Secado y Demanda Cruzada (Por hora)
    tasa_secado = 0.0
    if ultima_hora_secado is None or (dt_actual - ultima_hora_secado).total_seconds() >= 3600:
        if ultimo_promedio_suelo is not None:
            # Tasa = (H_anterior - H_actual) / 1 hora
            tasa_secado = ultimo_promedio_suelo - prom_hum_suelo
            cliente.publish(TOPICOS_SALIDA["tasa_secado"], str(round(tasa_secado, 2)), qos=1)
        
        ultimo_promedio_suelo = prom_hum_suelo
        ultima_hora_secado = dt_actual

    # Publicaciones MQTT
    cliente.publish(TOPICOS_SALIDA["temp_prom"], str(round(prom_temp, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_aire_prom"], str(round(prom_hum_aire, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpv"], str(dpv), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpd"], str(dpd), qos=1)
    cliente.publish(TOPICOS_SALIDA["gdd"], str(round(gdd_acumulado, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_suelo_prom"], str(round(prom_hum_suelo, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_suelo_estado"], estado_suelo, qos=1)
    
    for key in buffers:
        buffers[key].clear()

cliente = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
cliente.username_pw_set(username=mqtt_user, password=mqtt_password)
cliente.on_connect = on_connect
cliente.on_message = on_message
cliente.connect(host=urlServidor, port=puerto)
cliente.loop_forever()