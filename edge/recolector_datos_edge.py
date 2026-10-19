import paho.mqtt.client as mqtt
from datetime import datetime
import temperatura_metricas
from edge_meta_data import urlServidor, puerto

# ==========================================
# CONFIGURACIÓN DEL CLIENTE Y SEGURIDAD
# ==========================================
id_cliente = "edge-gateway-principal"

# Credenciales ACL para el Nodo Edge (Debe tener permisos de Lectura y Escritura)
mqtt_user = "edge_node"
mqtt_password = "password_seguro_edge"

# ==========================================
# TÓPICOS DE SUSCRIPCIÓN (Entrada cruda QoS 1)
# ==========================================
TOPICOS_ENTRADA = [
    ("campo1/parcelas/maiz1/temperatura/centigrados", 1),
    ("campo1/parcelas/maiz1/humedad/aire", 1),
    ("campo1/parcelas/parcela1/humedad/suelo", 1),
    ("campo1/invernaderos/invernadero1/luminosidad", 1)
]

# ==========================================
# TÓPICOS DE PUBLICACIÓN (Salida procesada)
# ==========================================
TOPICOS_SALIDA = {
    "temp_prom": "campo1/edge/parcelas/maiz1/temperatura/promedio",
    "hum_aire_prom": "campo1/edge/parcelas/maiz1/humedad_aire/promedio",
    "dpv": "campo1/edge/parcelas/maiz1/dpv",
    "dpd": "campo1/edge/parcelas/maiz1/dpd",
    "hum_suelo_prom": "campo1/edge/parcelas/parcela1/humedad_suelo/promedio",
    "lum_prom": "campo1/edge/invernaderos/invernadero1/luminosidad/promedio"
}

# ==========================================
# VARIABLES GLOBALES Y BUFFERS
# ==========================================
buffers = {
    "campo1/parcelas/maiz1/temperatura/centigrados": [],
    "campo1/parcelas/maiz1/humedad/aire": [],
    "campo1/parcelas/parcela1/humedad/suelo": [],
    "campo1/invernaderos/invernadero1/luminosidad": []
}
ventana_actual = None

def obtener_ventana_15_minutos(dt: datetime) -> datetime:
    """Redondea la fecha al bloque de 15 minutos más cercano."""
    minuto_redondeado = (dt.minute // 15) * 15
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

def calcular_promedio(lista):
    """Retorna el promedio de una lista, o 0.0 si está vacía."""
    return sum(lista) / len(lista) if lista else 0.0

def on_connect(cliente, userdata, flags, reason_code, properties=None):
    print(f"Edge conectado al broker MQTT con código {reason_code}")
    # Suscripción a todos los tópicos de entrada
    cliente.subscribe(TOPICOS_ENTRADA)
    print("Suscrito a todos los sensores.")

def on_message(cliente, userdata, message):
    global buffers, ventana_actual
    
    payload = message.payload.decode('utf-8')
    topico = message.topic
    
    try:
        # Formato esperado: "18/03/2023 12:24:01 29.00"
        str_fecha = payload[:19]
        str_valor = payload[19:].strip()
        dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
        valor = float(str_valor)
    except ValueError as e:
        print(f"Error parseando payload: '{payload}' en {topico}. Error: {e}")
        return

    ventana_mensaje = obtener_ventana_15_minutos(dt_mensaje)
    
    if ventana_actual is None:
        ventana_actual = ventana_mensaje

    # Lógica de cierre de ventana: procesa todo si llega un mensaje del siguiente bloque
    if ventana_mensaje > ventana_actual:
        procesar_y_publicar_ventana(cliente, ventana_actual)
        ventana_actual = ventana_mensaje

    # Almacenar en el buffer correspondiente
    if topico in buffers:
        print(f"[{str_fecha}] Recibido en {topico.split('/')[-1]}: {valor}")
        buffers[topico].append(valor)

def procesar_y_publicar_ventana(cliente, ventana):
    global buffers
    print(f"\n--- CIERRE DE VENTANA EDGE: {ventana.strftime('%H:%M')} ---")
    
    # 1. Calcular promedios descriptivos
    prom_temp = calcular_promedio(buffers["campo1/parcelas/maiz1/temperatura/centigrados"])
    prom_hum_aire = calcular_promedio(buffers["campo1/parcelas/maiz1/humedad/aire"])
    prom_hum_suelo = calcular_promedio(buffers["campo1/parcelas/parcela1/humedad/suelo"])
    prom_lum = calcular_promedio(buffers["campo1/invernaderos/invernadero1/luminosidad"])
    
    # 2. Calcular métricas complejas (Solo si hay datos de temp y hum_aire válidos)
    if prom_temp > 0 and prom_hum_aire > 0:
        dpv = temperatura_metricas.calcular_dpv(prom_temp, prom_hum_aire)
        dpd = temperatura_metricas.calcular_dpd(prom_temp, prom_hum_aire)
    else:
        dpv = dpd = 0.0

    print(f"Promedios -> Temp: {prom_temp:.2f}°C | Hum Aire: {prom_hum_aire:.2f}% | Hum Suelo: {prom_hum_suelo:.2f}% | Lum: {prom_lum:.2f}%")
    print(f"Métricas  -> DPV: {dpv} kPa | DPD: {dpd} °C")
    
    # 3. Publicar hacia el Dashboard con QoS 1
    # Nota: se descomentan los envíos para que lleguen al dashboard
    cliente.publish(TOPICOS_SALIDA["temp_prom"], str(round(prom_temp, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_aire_prom"], str(round(prom_hum_aire, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpv"], str(dpv), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpd"], str(dpd), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_suelo_prom"], str(round(prom_hum_suelo, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["lum_prom"], str(round(prom_lum, 2)), qos=1)
    
    # 4. Limpiar buffers para la siguiente ventana
    for key in buffers:
        buffers[key].clear()

# ==========================================
# INICIO DEL NODO EDGE
# ==========================================
# Configuración con Sesión Persistente
cliente = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

# Configurar credenciales ACL
cliente.username_pw_set(username=mqtt_user, password=mqtt_password)

cliente.on_connect = on_connect
cliente.on_message = on_message

print("Iniciando Nodo Edge Intermedio...")
cliente.connect(host=urlServidor, port=puerto)
cliente.loop_forever()