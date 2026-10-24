import paho.mqtt.client as mqtt
from datetime import datetime
from collections import deque
import temperatura_metricas
import json
import csv
import os
from edge_meta_data import urlServidor, puerto

id_cliente = "edge-gateway-principal"
mqtt_user = "edge_node"
mqtt_password = "password_seguro_edge"

# ==========================================================
# CONFIGURACIÓN DE TIEMPOS
#   MODO_DEMO = True  -> ciclos cortos para comprobar el sistema rápido
#   MODO_DEMO = False -> valores pensados para operación real
MODO_DEMO = True

VENTANA_CLIMA_SEG = 60                 # temperatura / humedad aire / DPV / GDD 

if MODO_DEMO:
    VENTANA_SUELO_SEG = 15             # promedio + semáforo + ETA "en vivo"
    VENTANA_HIST_SUELO_SEG = 60        # una fila en el CSV de suelo cada minuto
    SPAN_TASA_SEG = 120                # tendencia usada para la tasa de secado (2 min)
else:
    VENTANA_SUELO_SEG = 60
    VENTANA_HIST_SUELO_SEG = 30 * 60   # una fila cada 30 min (igual que luminosidad)
    SPAN_TASA_SEG = 3600               # tendencia de 1 hora

# ---- Umbrales de suelo (se ajustan tras calibrar el terreno) ----
PUNTO_MARCHITEZ = 30.0     # < 30 %  -> Rojo
CAPACIDAD_CAMPO = 50.0     # 50-79 % -> Verde
SATURACION = 80.0          # >= 80 % -> Azul
MIN_PUNTOS_TASA = 3        # mínimo de promedios de ventana para estimar tendencia
UMBRAL_CAMBIO_PTS = 1.0    # cambio total menor a esto en el SPAN = "estable" (filtra ruido ADC)
DPV_DEMANDA_ALTA = 1.2     # kPa: a partir de aquí el aire "exige" agua (zona naranja/roja del DPV)
ETA_CRITICA_H = 2.0        # horas a marchitez para alerta roja (si además hay DPV alto)
ETA_ALERTA_H = 6.0         # horas a marchitez para alerta amarilla
SALTO_RIEGO_PTS = 8.0      # subida entre dos registros del histórico que se cuenta como riego/lluvia

TOPICO_SUELO = "campo1/parcelas/parcela1/humedad/suelo"
TOPICO_REQUEST_HISTORIAL = "campo1/dashboard/request/historial"

TOPICOS_ENTRADA = [
    ("campo1/parcelas/maiz1/temperatura/centigrados", 1),
    ("campo1/parcelas/maiz1/humedad/aire", 1),
    (TOPICO_SUELO, 1),
    ("campo1/invernaderos/invernadero1/luminosidad", 1),
    (TOPICO_REQUEST_HISTORIAL, 1)
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
    "tiempo_marchitez": "campo1/edge/parcelas/parcela1/humedad_suelo/tiempo_marchitez",
    "hum_suelo_historial": "campo1/edge/parcelas/parcela1/humedad_suelo/historial",
    "lum_prom": "campo1/edge/invernaderos/invernadero1/luminosidad/promedio",
    "lum_estado": "campo1/edge/invernaderos/invernadero1/luminosidad/estado",
    "lum_historial": "campo1/edge/invernaderos/invernadero1/luminosidad/historial"
}

# Buffers de clima (el suelo ahora tiene su propio flujo más abajo)
buffers = {
    "campo1/parcelas/maiz1/temperatura/centigrados": [],
    "campo1/parcelas/maiz1/humedad/aire": []
}
ventana_actual = None

# Variables para almacenamiento histórico de LDR
buffer_lum_30m = []
ventana_30m_actual = None
ARCHIVO_HISTORICO = "historico_luminosidad.csv"

# Variables para métricas acumulativas de clima
gdd_acumulado = 0.0
ultimo_dpv = None   # lo usa el flujo de suelo para el riesgo cruzado

# Estado del flujo de humedad de suelo
ARCHIVO_HISTORICO_SUELO = "historico_humedad_suelo.csv"
buffer_suelo = []                 # lecturas de la ventana "en vivo"
ventana_suelo_actual = None
buffer_suelo_hist = []            # lecturas de la ventana del histórico (CSV)
ventana_suelo_hist_actual = None
muestras_tasa = deque()           # (inicio_ventana, promedio) dentro del SPAN_TASA_SEG


def inicializar_csv():
    if not os.path.exists(ARCHIVO_HISTORICO):
        with open(ARCHIVO_HISTORICO, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Fecha", "Hora", "Luminosidad"])
    if not os.path.exists(ARCHIVO_HISTORICO_SUELO):
        with open(ARCHIVO_HISTORICO_SUELO, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Fecha", "Hora", "Humedad"])

def obtener_ventana_minutos(dt: datetime, minutos: int) -> datetime:
    minuto_redondeado = (dt.minute // minutos) * minutos
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

def obtener_ventana_seg(dt: datetime, segundos: int) -> datetime:
    """Inicio de la ventana de `segundos` que contiene a dt (sirve para 15 s, 1 min, 30 min...)."""
    seg_dia = dt.hour * 3600 + dt.minute * 60 + dt.second
    seg_dia -= seg_dia % segundos
    return dt.replace(hour=seg_dia // 3600, minute=(seg_dia % 3600) // 60,
                      second=seg_dia % 60, microsecond=0)

def calcular_promedio(lista):
    return sum(lista) / len(lista) if lista else 0.0

def leer_historial_hoy(fecha_hoy):
    datos_hoy = {}
    if not os.path.exists(ARCHIVO_HISTORICO): return datos_hoy
    
    with open(ARCHIVO_HISTORICO, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["Fecha"] == fecha_hoy:
                hora_corta = row["Hora"][:5] 
                datos_hoy[hora_corta] = float(row["Luminosidad"])
    return datos_hoy

def despachar_historial_hoy(cliente, dt_actual):
    fecha_hoy = dt_actual.strftime("%Y-%m-%d")
    datos = leer_historial_hoy(fecha_hoy)
    cliente.publish(TOPICOS_SALIDA["lum_historial"], json.dumps(datos), qos=1)

# ==========================================================
# HUMEDAD DE SUELO
#   EN VIVO  : promedio de ventana, semáforo, tasa de secado,
#              tiempo estimado a marchitez, riesgo cruzado con DPV
#   HISTÓRICO: CSV (promedios de VENTANA_HIST_SUELO_SEG) + resumen del día
# ==========================================================
def clasificar_suelo(h):
    if h >= SATURACION: return "Azul|Suelo saturado y sin oxígeno.|Peligro de pudrición; no regar."
    if h >= CAPACIDAD_CAMPO: return "Verde|Rango óptimo para raíces.|Capacidad de Campo."
    if h >= PUNTO_MARCHITEZ: return "Amarillo|El suelo se está secando.|Estrés Leve. Monitorear riego."
    return "Rojo|Condición crítica.|Punto de Marchitez. Regar inmediatamente."

def calcular_tasa_secado():
    """
    Regresión lineal sobre los promedios de ventana de los últimos SPAN_TASA_SEG.
    Devuelve la pérdida de humedad en puntos porcentuales por HORA
    (positivo = secándose, negativo = humedeciéndose, 0.0 = estable) o None si aún
    no hay suficientes datos. Usar una regresión (y no 2 puntos) evita que el ruido
    del ADC se dispare al extrapolar a una hora.
    """
    if len(muestras_tasa) < MIN_PUNTOS_TASA:
        return None
    t0 = muestras_tasa[0][0]
    xs = [(t - t0).total_seconds() for t, _ in muestras_tasa]
    ys = [v for _, v in muestras_tasa]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    pendiente = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx   # % por segundo
    if abs(pendiente * SPAN_TASA_SEG) < UMBRAL_CAMBIO_PTS:
        return 0.0
    return -pendiente * 3600.0

def estimar_tiempo_marchitez(prom, tasa):
    """Devuelve (texto para el dashboard, horas o None)."""
    if prom <= PUNTO_MARCHITEZ:
        return "Ahora mismo", 0.0
    if tasa is None:
        return "Calculando...", None
    if tasa <= 0:
        return "No se está secando", None
    horas = (prom - PUNTO_MARCHITEZ) / tasa
    if horas > 48:
        return "Más de 2 días", horas
    if horas < 1:
        return f"≈ {round(horas * 60)} min", horas
    return f"≈ {horas:.1f} h", horas

def evaluar_riesgo_cruzado(prom, horas, dpv):
    """
    Cruza la curva de secado del suelo con la demanda atmosférica (DPV).
    Devuelve (color, mensaje) o (None, None) si no hay riesgo adicional.
    """
    demanda_alta = dpv is not None and dpv >= DPV_DEMANDA_ALTA
    if prom <= PUNTO_MARCHITEZ:
        return "Rojo", "Suelo en punto de marchitez. Regar de inmediato."
    if horas is not None and horas <= ETA_CRITICA_H and demanda_alta:
        return "Rojo", "Se seca rápido y el aire está muy seco. Regar de inmediato."
    if horas is not None and horas <= ETA_ALERTA_H:
        return "Amarillo", "Se está secando: conviene programar el riego pronto."
    if demanda_alta and prom < CAPACIDAD_CAMPO:
        return "Amarillo", "Suelo algo seco y el aire está muy seco. Vigilar."
    return None, None

def estado_suelo_final(prom, horas, dpv):
    """
    UN solo semáforo para el dashboard: el de humedad (clasificar_suelo), escalado si la
    tendencia de secado + la demanda del aire indican más riesgo. Formato: Color|Diagnóstico|Acción
    """
    color, diag, accion = clasificar_suelo(prom).split("|")
    rangos = {"Verde": 0, "Amarillo": 1, "Rojo": 2}
    r_color, r_msg = evaluar_riesgo_cruzado(prom, horas, dpv)
    if r_color and color in rangos and rangos[r_color] >= rangos[color]:
        color, diag, accion = r_color, "Riesgo por tendencia de secado y demanda del aire.", r_msg
    return f"{color}|{diag}|{accion}"

def cerrar_ventana_suelo(cliente, ventana):
    """Cierra la ventana 'en vivo': promedio, semáforo, tasa, ETA y riesgo cruzado."""
    global buffer_suelo
    if not buffer_suelo:
        return
    prom = calcular_promedio(buffer_suelo)
    buffer_suelo.clear()

    # Un riego/lluvia (subida brusca) inicia una curva de secado nueva: la tendencia anterior
    # ya no aplica y extrapolar el salto a "% por hora" daría valores absurdos.
    if muestras_tasa and prom - muestras_tasa[-1][1] >= SALTO_RIEGO_PTS:
        muestras_tasa.clear()
    muestras_tasa.append((ventana, prom))
    while (ventana - muestras_tasa[0][0]).total_seconds() > SPAN_TASA_SEG:
        muestras_tasa.popleft()

    tasa = calcular_tasa_secado()
    txt_eta, horas = estimar_tiempo_marchitez(prom, tasa)

    print(f"[SUELO] Ventana {ventana.strftime('%H:%M:%S')}: {prom:.2f}% | "
          f"tasa={None if tasa is None else round(tasa, 2)} %/h | marchitez: {txt_eta}")

    cliente.publish(TOPICOS_SALIDA["hum_suelo_prom"], str(round(prom, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_suelo_estado"], estado_suelo_final(prom, horas, ultimo_dpv), qos=1)
    if tasa is not None:
        cliente.publish(TOPICOS_SALIDA["tasa_secado"], str(round(tasa, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["tiempo_marchitez"], txt_eta, qos=1)

def formato_hora_suelo(hora):
    # Si el histórico guarda minutos exactos basta HH:MM; si no, se conservan los segundos
    return hora[:5] if VENTANA_HIST_SUELO_SEG % 60 == 0 else hora

def leer_historial_suelo(fecha_hoy):
    datos_hoy = {}
    if not os.path.exists(ARCHIVO_HISTORICO_SUELO): return datos_hoy
    with open(ARCHIVO_HISTORICO_SUELO, mode='r') as file:
        for row in csv.DictReader(file):
            if row["Fecha"] == fecha_hoy:
                datos_hoy[formato_hora_suelo(row["Hora"])] = float(row["Humedad"])
    return datos_hoy

def calcular_resumen_suelo(valores):
    if not valores:
        return {}
    optimos = sum(1 for v in valores if CAPACIDAD_CAMPO <= v < SATURACION)
    riegos = sum(1 for a, b in zip(valores, valores[1:]) if b - a >= SALTO_RIEGO_PTS)
    return {
        "promedio": round(calcular_promedio(valores), 1),
        "min": round(min(valores), 1),
        "max": round(max(valores), 1),
        "pct_optimo": round(100 * optimos / len(valores)),
        "riegos": riegos
    }

def despachar_historial_suelo(cliente, dt_actual):
    serie = leer_historial_suelo(dt_actual.strftime("%Y-%m-%d"))
    payload = {"serie": serie, "resumen": calcular_resumen_suelo(list(serie.values()))}
    cliente.publish(TOPICOS_SALIDA["hum_suelo_historial"], json.dumps(payload), qos=1)

def registrar_historico_suelo(cliente, ventana, valores):
    if not valores:
        return
    prom = calcular_promedio(valores)
    with open(ARCHIVO_HISTORICO_SUELO, mode='a', newline='') as file:
        csv.writer(file).writerow([ventana.strftime("%Y-%m-%d"), ventana.strftime("%H:%M:%S"), round(prom, 2)])
    print(f"[EDGE] Histórico de suelo guardado ({ventana.strftime('%H:%M:%S')}): {round(prom, 2)}%")
    despachar_historial_suelo(cliente, ventana)

def manejar_suelo(cliente, dt_mensaje, valor):
    global ventana_suelo_actual, ventana_suelo_hist_actual
    # --- Ventana "en vivo" (cierra primero, luego agrega la lectura a la ventana nueva) ---
    ventana = obtener_ventana_seg(dt_mensaje, VENTANA_SUELO_SEG)
    if ventana_suelo_actual is None:
        ventana_suelo_actual = ventana
    if ventana > ventana_suelo_actual:
        cerrar_ventana_suelo(cliente, ventana_suelo_actual)
        ventana_suelo_actual = ventana
    buffer_suelo.append(valor)

    # --- Ventana del histórico (CSV) ---
    ventana_h = obtener_ventana_seg(dt_mensaje, VENTANA_HIST_SUELO_SEG)
    if ventana_suelo_hist_actual is None:
        ventana_suelo_hist_actual = ventana_h
    if ventana_h > ventana_suelo_hist_actual:
        registrar_historico_suelo(cliente, ventana_suelo_hist_actual, buffer_suelo_hist)
        buffer_suelo_hist.clear()
        ventana_suelo_hist_actual = ventana_h
    buffer_suelo_hist.append(valor)

# ==========================================================
# MQTT
# ==========================================================
def on_connect(cliente, userdata, flags, reason_code, properties=None):
    print(f"Edge conectado al broker MQTT con código {reason_code}")
    cliente.subscribe(TOPICOS_ENTRADA)

def on_message(cliente, userdata, message):
    global buffers, ventana_actual, buffer_lum_30m, ventana_30m_actual
    payload = message.payload.decode('utf-8')
    topico = message.topic
    
    if topico == TOPICO_REQUEST_HISTORIAL:
        print("\n[REQUEST] Despachando historial histórico a Dashboard...")
        ahora = datetime.now()
        despachar_historial_hoy(cliente, ahora)
        despachar_historial_suelo(cliente, ahora)
        return

    try:
        str_fecha = payload[:19]
        str_valor = payload[19:].strip()
        dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
        valor = float(str_valor)
    except ValueError:
        return

    if topico == TOPICO_SUELO:
        # El ESP32 publica con retain=true: al conectarse el Edge recibe la última lectura
        # guardada en el broker (posiblemente de hace horas). No debe entrar al histórico.
        if message.retain:
            return
        manejar_suelo(cliente, dt_mensaje, valor)
        return

    if topico == "campo1/invernaderos/invernadero1/luminosidad":
        if valor <= 20: estado_lum = "Gris|Fotosíntesis mínima o nula.|Condición normal de noche. Si ocurre de día, encender iluminación artificial o revisar obstrucciones."
        elif valor <= 50: estado_lum = "Azul|Adecuado para plantas de sombra, pero insuficiente para maximizar el rendimiento de maíz/tomate.|Retirar mallas sombra si están desplegadas."
        elif valor <= 85: estado_lum = "Verde|Rango ideal. Tasa de asimilación fotosintética máxima sin generar estrés térmico.|Condiciones ideales, no se requiere acción."
        else: estado_lum = "Rojo|Radiación extrema. Alto riesgo de fotoinhibición y quemaduras en el tejido vegetal.|Precaución. Desplegar malla sombra al 30% o 50% inmediatamente."

        cliente.publish(TOPICOS_SALIDA["lum_prom"], str(round(valor, 2)), qos=1)
        cliente.publish(TOPICOS_SALIDA["lum_estado"], estado_lum, qos=1)
        
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
            
            despachar_historial_hoy(cliente, dt_mensaje)
            
        return

    # ==========================================================
    # Ventana de CLIMA (temperatura y humedad del aire)
    # ==========================================================
    ventana_mensaje = obtener_ventana_seg(dt_mensaje, VENTANA_CLIMA_SEG)
    if ventana_actual is None:
        ventana_actual = ventana_mensaje

    if ventana_mensaje > ventana_actual:
        procesar_y_publicar_ventana(cliente, ventana_actual, dt_mensaje)
        ventana_actual = ventana_mensaje

    if topico in buffers:
        buffers[topico].append(valor)

def procesar_y_publicar_ventana(cliente, ventana, dt_actual):
    global buffers, gdd_acumulado, ultimo_dpv
    print(f"\n--- CIERRE DE VENTANA CLIMA EDGE ({VENTANA_CLIMA_SEG} s): {ventana.strftime('%H:%M:%S')} ---")
    
    prom_temp = calcular_promedio(buffers["campo1/parcelas/maiz1/temperatura/centigrados"])
    prom_hum_aire = calcular_promedio(buffers["campo1/parcelas/maiz1/humedad/aire"])
    
    if prom_temp > 0 and prom_hum_aire > 0:
        dpv = temperatura_metricas.calcular_dpv(prom_temp, prom_hum_aire)
        dpd = temperatura_metricas.calcular_dpd(prom_temp, prom_hum_aire)
        try:
            ultimo_dpv = float(dpv)    # lo consume el riesgo cruzado del suelo
        except (TypeError, ValueError):
            pass
    else:
        dpv = dpd = 0.0

    # GDD: cada ventana aporta (T - Tb) * (duración de la ventana / 1 día)
    gdh = prom_temp - 10.0
    if gdh < 0: gdh = 0 
    gdd_acumulado += gdh * VENTANA_CLIMA_SEG / 86400.0

    cliente.publish(TOPICOS_SALIDA["temp_prom"], str(round(prom_temp, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_aire_prom"], str(round(prom_hum_aire, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpv"], str(dpv), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpd"], str(dpd), qos=1)
    cliente.publish(TOPICOS_SALIDA["gdd"], str(round(gdd_acumulado, 4)), qos=1)
    
    for key in buffers:
        buffers[key].clear()

if __name__ == "__main__":
    inicializar_csv()
    cliente = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    cliente.username_pw_set(username=mqtt_user, password=mqtt_password)
    cliente.on_connect = on_connect
    cliente.on_message = on_message
    cliente.connect(host=urlServidor, port=puerto)
    cliente.loop_forever()