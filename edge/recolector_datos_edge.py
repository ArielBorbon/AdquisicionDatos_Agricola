import paho.mqtt.client as mqtt
from datetime import datetime
import temperatura_metricas
import json
import csv
import os
from edge_meta_data import urlServidor, puerto

id_cliente = "edge-gateway-principal"
mqtt_user = "edge_node"
mqtt_password = "password_seguro_edge"

TOPICOS_ENTRADA = [
    ("campo1/parcelas/maiz1/temperatura/centigrados", 1),
    ("campo1/parcelas/maiz1/humedad/aire", 1),
    ("campo1/parcelas/parcela1/humedad/suelo", 1),
    ("campo1/invernaderos/invernadero1/luminosidad", 1),
    ("campo1/dashboard/request/historial", 1) # Tópico para escuchar solicitudes del Dashboard
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
    "lum_estado": "campo1/edge/invernaderos/invernadero1/luminosidad/estado",
    "lum_historial": "campo1/edge/invernaderos/invernadero1/luminosidad/historial" # Tópico de JSON histórico
}

buffers = {
    "campo1/parcelas/maiz1/temperatura/centigrados": [],
    "campo1/parcelas/maiz1/humedad/aire": [],
    "campo1/parcelas/parcela1/humedad/suelo": []
}
ventana_actual = None

# Variables para almacenamiento histórico de LDR
buffer_lum_30m = []
ventana_30m_actual = None
ARCHIVO_HISTORICO = "historico_luminosidad.csv"

# Variables para métricas acumulativas
gdd_acumulado = 0.0
ultimo_promedio_suelo = None
ultima_hora_secado = None

def inicializar_csv():
    if not os.path.exists(ARCHIVO_HISTORICO):
        with open(ARCHIVO_HISTORICO, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Fecha", "Hora", "Luminosidad"])

def obtener_ventana_minutos(dt: datetime, minutos: int) -> datetime:
    minuto_redondeado = (dt.minute // minutos) * minutos
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

def calcular_promedio(lista):
    return sum(lista) / len(lista) if lista else 0.0

def leer_historial_hoy(fecha_hoy):
    datos_hoy = {}
    if not os.path.exists(ARCHIVO_HISTORICO): return datos_hoy
    
    with open(ARCHIVO_HISTORICO, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["Fecha"] == fecha_hoy:
                hora_corta = row["Hora"][:5] # Extrae HH:MM para no saturar la gráfica
                datos_hoy[hora_corta] = float(row["Luminosidad"])
    return datos_hoy

def despachar_historial_hoy(cliente, dt_actual):
    fecha_hoy = dt_actual.strftime("%Y-%m-%d")
    datos = leer_historial_hoy(fecha_hoy)
    # Enviar el diccionario como JSON string
    cliente.publish(TOPICOS_SALIDA["lum_historial"], json.dumps(datos), qos=1)

def on_connect(cliente, userdata, flags, reason_code, properties=None):
    print(f"Edge conectado al broker MQTT con código {reason_code}")
    cliente.subscribe(TOPICOS_ENTRADA)

def on_message(cliente, userdata, message):
    global buffers, ventana_actual, buffer_lum_30m, ventana_30m_actual
    payload = message.payload.decode('utf-8')
    topico = message.topic
    
    # 1. Petición manual del dashboard
    if topico == "campo1/dashboard/request/historial":
        print("\n[REQUEST] Despachando historial histórico a Dashboard...")
        despachar_historial_hoy(cliente, datetime.now())
        return

    try:
        str_fecha = payload[:19]
        str_valor = payload[19:].strip()
        dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
        valor = float(str_valor)
    except ValueError:
        return

    # 2. Lógica del Sensor LDR (Fast-track y Guardado Histórico)
    if topico == "campo1/invernaderos/invernadero1/luminosidad":
        # -- Semáforo en vivo --
        if valor <= 20: estado_lum = "Gris|Fotosíntesis mínima o nula.|Condición normal de noche."
        elif valor <= 50: estado_lum = "Azul|Adecuado para sombra.|Retirar mallas sombra si están desplegadas."
        elif valor <= 85: estado_lum = "Verde|Rango ideal.|Condiciones ideales, no se requiere acción."
        else: estado_lum = "Rojo|Radiación extrema.|Precaución. Desplegar malla sombra al 30% inmediatamente."

        cliente.publish(TOPICOS_SALIDA["lum_prom"], str(round(valor, 2)), qos=1)
        cliente.publish(TOPICOS_SALIDA["lum_estado"], estado_lum, qos=1)
        
        # -- Lógica de almacenamiento en ventanas de 30 min --
        ventana_30m = obtener_ventana_minutos(dt_mensaje, 30)
        if ventana_30m_actual is None:
            ventana_30m_actual = ventana_30m

        buffer_lum_30m.append(valor)

        if ventana_30m > ventana_30m_actual:
            prom_30m = calcular_promedio(buffer_lum_30m)
            fecha_str = ventana_30m_actual.strftime("%Y-%m-%d")
            hora_str = ventana_30m_actual.strftime("%H:%M:%S")
            
            with open(ARCHIVO_HISTORICO, mode='a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([fecha_str, hora_str, round(prom_30m, 2)])
            
            print(f"[EDGE] Histórico guardado ({hora_str}): {round(prom_30m, 2)}%")
            buffer_lum_30m.clear()
            ventana_30m_actual = ventana_30m
            
            # Despachar automáticamente a toda la red
            despachar_historial_hoy(cliente, dt_mensaje)
            
        return

    # 3. Lógica de Ventanas de 15 minutos (Clima y Suelo)
    ventana_mensaje = obtener_ventana_minutos(dt_mensaje, 15)
    if ventana_actual is None:
        ventana_actual = ventana_mensaje

    if ventana_mensaje > ventana_actual:
        procesar_y_publicar_ventana(cliente, ventana_actual, dt_mensaje)
        ventana_actual = ventana_mensaje

    if topico in buffers:
        buffers[topico].append(valor)

def procesar_y_publicar_ventana(cliente, ventana, dt_actual):
    global buffers, gdd_acumulado, ultimo_promedio_suelo, ultima_hora_secado
    print(f"\n--- CIERRE DE VENTANA CLIMA EDGE: {ventana.strftime('%H:%M')} ---")
    
    prom_temp = calcular_promedio(buffers["campo1/parcelas/maiz1/temperatura/centigrados"])
    prom_hum_aire = calcular_promedio(buffers["campo1/parcelas/maiz1/humedad/aire"])
    prom_hum_suelo = calcular_promedio(buffers["campo1/parcelas/parcela1/humedad/suelo"])
    
    if prom_temp > 0 and prom_hum_aire > 0:
        dpv = temperatura_metricas.calcular_dpv(prom_temp, prom_hum_aire)
        dpd = temperatura_metricas.calcular_dpd(prom_temp, prom_hum_aire)
    else:
        dpv = dpd = 0.0

    gdh = prom_temp - 10.0
    if gdh < 0: gdh = 0 
    gdd_acumulado += gdh / (24 * 4) 
    
    if prom_hum_suelo >= 80: estado_suelo = "Azul|Suelo saturado y sin oxígeno.|Peligro de pudrición; no regar."
    elif prom_hum_suelo >= 50: estado_suelo = "Verde|Rango óptimo para raíces.|Capacidad de Campo."
    elif prom_hum_suelo >= 30: estado_suelo = "Amarillo|El suelo se está secando.|Estrés Leve. Monitorear riego."
    else: estado_suelo = "Rojo|Condición crítica.|Punto de Marchitez. Regar inmediatamente."

    tasa_secado = 0.0
    if ultima_hora_secado is None or (dt_actual - ultima_hora_secado).total_seconds() >= 3600:
        if ultimo_promedio_suelo is not None:
            tasa_secado = ultimo_promedio_suelo - prom_hum_suelo
            cliente.publish(TOPICOS_SALIDA["tasa_secado"], str(round(tasa_secado, 2)), qos=1)
        ultimo_promedio_suelo = prom_hum_suelo
        ultima_hora_secado = dt_actual

    cliente.publish(TOPICOS_SALIDA["temp_prom"], str(round(prom_temp, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_aire_prom"], str(round(prom_hum_aire, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpv"], str(dpv), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpd"], str(dpd), qos=1)
    cliente.publish(TOPICOS_SALIDA["gdd"], str(round(gdd_acumulado, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_suelo_prom"], str(round(prom_hum_suelo, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_suelo_estado"], estado_suelo, qos=1)
    
    for key in buffers:
        buffers[key].clear()

inicializar_csv()
cliente = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
cliente.username_pw_set(username=mqtt_user, password=mqtt_password)
cliente.on_connect = on_connect
cliente.on_message = on_message
cliente.connect(host=urlServidor, port=puerto)
cliente.loop_forever()