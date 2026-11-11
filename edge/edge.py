import random
import paho.mqtt.client as mqtt  # type: ignore
from datetime import datetime, timedelta
from collections import deque
import temperatura_metricas
import json
import csv
import os
from edge_meta_data import urlServidor, urlRabbitMQ, puerto, puertoRabbitMQ

id_cliente = "edge-gateway-principal"
mqtt_user = "edge_node"
mqtt_password = "password_seguro_edge"

# ==========================================================
# CONFIGURACIÓN DE TIEMPOS
#   MODO_DEMO = True  -> ciclos cortos para pruebas rápidas
#   MODO_DEMO = False -> tiempos para producción real
# ==========================================================
MODO_DEMO = True

if MODO_DEMO:
    VENTANA_CLIMA_SEG = 60                 # Temperatura / Humedad Aire / DPV / DPD (1 min)
    VENTANA_GDD_SEG = 60 * 5               # GDD (5 min)
    VENTANA_SUELO_SEG = 15                 # Promedio + semáforo en vivo (15 s)
    VENTANA_HIST_SUELO_SEG = 60            # Fila en CSV de suelo (1 min)
    SPAN_TASA_SEG = 120                    # Ventana de tendencia para tasa de secado (2 min)
else:
    VENTANA_CLIMA_SEG = 15 * 60            # Clima (15 min)
    VENTANA_GDD_SEG = 3600                 # GDD (1 hora)
    VENTANA_SUELO_SEG = 60                 # Promedio suelo (1 min)
    VENTANA_HIST_SUELO_SEG = 30 * 60       # Fila en CSV de suelo (30 min)
    SPAN_TASA_SEG = 3600                   # Ventana de tendencia (1 hora)

# ---- Umbrales de Humedad del Suelo (% VWC) ----
PUNTO_MARCHITEZ = 30.0     # < 30 %  -> Rojo (Marchitez)
CAPACIDAD_CAMPO = 50.0     # 50-79 % -> Verde (Óptimo)
SATURACION = 80.0          # >= 80 % -> Azul (Asfixia radicular)

# ---- Parámetros de Cálculo de Tasa y Demanda Cruzada ----
MIN_PUNTOS_TASA = 3        # Mínimo de promedios para estimar regresión lineal
UMBRAL_CAMBIO_PTS = 1.0    # Variación mínima (%) en SPAN_TASA para no considerar "Estable"
DPV_DEMANDA_ALTA = 1.2     # kPa: Umbral donde el aire exige evaporación alta
ETA_CRITICA_H = 2.0        # Horas a marchitez para disparar Alerta Roja
ETA_ALERTA_H = 6.0         # Horas a marchitez para disparar Alerta Amarilla
SALTO_RIEGO_PTS = 8.0      # Incremento brusco que reinicia la curva por evento de riego

# Tópicos MQTT
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
    "demanda_cruzada": "campo1/edge/parcelas/parcela1/humedad_suelo/demanda_cruzada",
    "tiempo_marchitez": "campo1/edge/parcelas/parcela1/humedad_suelo/tiempo_marchitez",
    "hum_suelo_historial": "campo1/edge/parcelas/parcela1/humedad_suelo/historial",
    "lum_prom": "campo1/edge/invernaderos/invernadero1/luminosidad/promedio",
    "lum_estado": "campo1/edge/invernaderos/invernadero1/luminosidad/estado",
    "lum_historial": "campo1/edge/invernaderos/invernadero1/luminosidad/historial",
    "gdd_historial_diario": "campo1/edge/parcelas/maiz1/gdd/historial_diario"
}

# Buffers de datos
buffers = {
    "campo1/parcelas/maiz1/temperatura/centigrados": [],
    "campo1/parcelas/maiz1/humedad/aire": []
}
ventana_actual = None
ventana_gdd_actual = None

# Etapas fenológicas del maíz (ordenadas de mayor a menor umbral)
ETAPAS_MAIZ = [
    {"gdd": 1600, "nombre": "R6 - Madurez Fisiológica", "desc": "Se forma una 'capa negra' en la base del grano, cortando la conexión vascular con la planta. El maíz está listo para la cosecha."},
    {"gdd": 1300, "nombre": "R5 - Dentado (Dent)", "desc": "El grano comienza a secarse en la parte superior, formando una hendidura o 'diente'."},
    {"gdd": 1150, "nombre": "R4 - Masoso (Dough)", "desc": "El líquido interno se espesa y adquiere una consistencia de masa."},
    {"gdd": 1000, "nombre": "R3 - Lechoso (Milk)", "desc": "El interior del grano se vuelve blanco y lechoso debido a la acumulación de almidón."},
    {"gdd": 850, "nombre": "R2 - Ampolla (Blister)", "desc": "Los granos parecen pequeñas ampollas blancas llenas de un líquido transparente."},
    {"gdd": 750, "nombre": "R1 - Floración / Sedas (Silking)", "desc": "Emergen los estigmas (pelos del elote). Ocurre la polinización. Es la etapa de mayor estrés térmico; un golpe de calor aquí causa aborto de granos."},
    {"gdd": 650, "nombre": "VT - Espigamiento (Tasseling)", "desc": "La última rama de la espiga (flor masculina) es completamente visible. Máxima vulnerabilidad al déficit hídrico (DPV alto)."},
    {"gdd": 450, "nombre": "V12 - Doceava hoja", "desc": "Se define el tamaño y número de granos por hilera. La demanda de agua se dispara drásticamente."},
    {"gdd": 340, "nombre": "V9 - Novena hoja", "desc": "Rápido crecimiento del tallo. Comienza una alta demanda de nitrógeno."},
    {"gdd": 235, "nombre": "V6 - Sexta hoja", "desc": "El punto de crecimiento sale a la superficie. Se define genéticamente el número máximo de hileras que tendrá la mazorca."},
    {"gdd": 150, "nombre": "V3 - Tercera hoja", "desc": "El punto de crecimiento sigue bajo tierra. La planta resiste heladas ligeras."},
    {"gdd": 65, "nombre": "VE - Emergencia", "desc": "La semilla germina y el primer coleóptilo rompe la superficie del suelo."},
    {"gdd": 0, "nombre": "Pre-emergencia", "desc": "La semilla se encuentra bajo tierra absorbiendo humedad e iniciando la germinación."}
]

def obtener_etapa_fenologica(gdd_actual):
    for etapa in ETAPAS_MAIZ:
        if gdd_actual >= etapa["gdd"]:
            return {"nombre": etapa["nombre"], "descripcion": etapa["desc"]}
    return {"nombre": "Desconocida", "descripcion": "Sin datos."}

# Archivos de persistencia CSV
DATA_PATH = "data/"
ARCHIVO_HISTORICO = f"{DATA_PATH}historico_luminosidad.csv"
ARCHIVO_HISTORICO_SUELO = f"{DATA_PATH}historico_humedad_suelo.csv"
ARCHIVO_HISTORICO_TEMP = f"{DATA_PATH}historico_temperatura.csv"
ARCHIVO_HISTORICO_HUM_AIRE = f"{DATA_PATH}historico_humedad_aire.csv"
ARCHIVO_HISTORICO_GDD = f"{DATA_PATH}historico_gdd.csv"

TEMP_MEDIA_MENSUAL = {
    1: 17.0, 2: 18.0, 3: 20.0, 4: 23.0,
    5: 27.0, 6: 30.0, 7: 31.0, 8: 31.0,
    9: 30.0, 10: 27.0, 11: 22.0, 12: 17.0
}
TEMP_BASE_MAIZ = 10.0

# Buffers de Iluminación
buffer_lum_30m = []
ventana_30m_actual = None
ultimo_despacho_grafica = None

# Acumuladores de Clima
def inicializar_gdd_historico():
    # 1. Definir el GDD objetivo aleatorio (basado en los rangos fenológicos del maíz)
    gdd_objetivo = random.choice([
        random.randint(0, 65), random.randint(65, 150), random.randint(150, 235),
        random.randint(235, 340), random.randint(340, 450), random.randint(450, 650),
        random.randint(650, 750), random.randint(750, 850), random.randint(850, 1000),
        random.randint(1000, 1150), random.randint(1150, 1300), random.randint(1300, 1600)
    ])
    
    # 2. Limpiar el historial previo en cada ejecución
    if os.path.exists(ARCHIVO_HISTORICO_GDD):
        os.remove(ARCHIVO_HISTORICO_GDD)
        
    fecha_actual = datetime.now()
    fecha_simulacion = fecha_actual - timedelta(days=1)
    
    gdd_acumulado_inverso = 0.0
    historial_inverso = []
    
    # 3. Viajar hacia atrás en el tiempo hasta alcanzar el GDD objetivo
    while gdd_acumulado_inverso < gdd_objetivo:
        mes = fecha_simulacion.month
        
        # Simular temperatura del día basada en la media del mes +/- 2°C de ruido natural
        t_promedio_dia = TEMP_MEDIA_MENSUAL[mes] + random.uniform(-2.0, 2.0)
        
        # Calcular el GDD de ese día (fórmula: T_prom - T_base)
        gdd_diario = max(0, t_promedio_dia - TEMP_BASE_MAIZ)
        gdd_acumulado_inverso += gdd_diario
        
        # Guardar en la lista temporal
        historial_inverso.append({
            "Fecha": fecha_simulacion.strftime("%Y-%m-%d"),
            "GDD": round(gdd_diario, 2)
        })
        
        fecha_simulacion -= timedelta(days=1)
        
    # 4. Invertir la lista para que quede del registro más antiguo al más reciente
    historial_cronologico = list(reversed(historial_inverso))
    
    # 5. Escribir el CSV recalculando el acumulado de forma progresiva
    acumulado_real = 0.0
    
    os.makedirs(DATA_PATH, exist_ok=True)
    with open(ARCHIVO_HISTORICO_GDD, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Fecha", "GDD", "GDD_Acumulado"])
        
        for registro in historial_cronologico:
            acumulado_real += registro["GDD"]
            writer.writerow([registro["Fecha"], registro["GDD"], round(acumulado_real, 2)])
            
    print(f"[SIMULACIÓN] Historial GDD generado. Objetivo: {gdd_objetivo}, Acumulado final: {round(acumulado_real, 2)}, Días simulados: {len(historial_cronologico)}")
    
    return acumulado_real

# Inicializar la variable global ejecutando la simulación
gdd_acumulado = inicializar_gdd_historico()
gdd_acumulado_anterior = gdd_acumulado # Añadir después de inicializar el histórico
ultimo_dpv = None  # Almacena el DPV más reciente para la demanda cruzada

# Buffers de Suelo
buffer_suelo = []
ventana_suelo_actual = None
buffer_suelo_hist = []
ventana_suelo_hist_actual = None
muestras_tasa = deque()  # Tuplas (datetime, promedio) para regresión de secado


def inicializar_csv():
    archivos_columnas = {
        ARCHIVO_HISTORICO: ["Fecha", "Hora", "Luminosidad"],
        ARCHIVO_HISTORICO_SUELO: ["Fecha", "Hora", "Humedad"],
        ARCHIVO_HISTORICO_TEMP: ["Fecha", "Hora", "Temperatura"],
        ARCHIVO_HISTORICO_HUM_AIRE: ["Fecha", "Hora", "Humedad_Aire"]
    }
    for archivo, columnas in archivos_columnas.items():
        if not os.path.exists(archivo):
            with open(archivo, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(columnas)

def obtener_ventana_minutos(dt: datetime, minutos: int) -> datetime:
    minuto_redondeado = (dt.minute // minutos) * minutos
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

def obtener_ventana_seg(dt: datetime, segundos: int) -> datetime:
    seg_dia = dt.hour * 3600 + dt.minute * 60 + dt.second
    seg_dia -= seg_dia % segundos
    return dt.replace(hour=seg_dia // 3600, minute=(seg_dia % 3600) // 60,
                      second=seg_dia % 60, microsecond=0)

def calcular_promedio(lista):
    return sum(lista) / len(lista) if lista else 0.0

def leer_historial_generico(archivo, fecha_hoy, columna_valor):
    datos_hoy = {}
    if not os.path.exists(archivo): return datos_hoy
    with open(archivo, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row["Fecha"] == fecha_hoy:
                hora_corta = row["Hora"][:5]
                datos_hoy[hora_corta] = float(row[columna_valor])
    return datos_hoy

def clasificar_estado_luminosidad(valor: float) -> str:
    if valor <= 20: return "Gris"
    if valor <= 50: return "Azul"
    if valor <= 85: return "Verde"
    return "Rojo"

def calcular_kpi_eficiencia_fotosintetica(valores) -> dict:
    conteo = {"Gris": 0, "Azul": 0, "Verde": 0, "Rojo": 0}
    for v in valores:
        estado = clasificar_estado_luminosidad(float(v))
        conteo[estado] += 1

    ventanas_diurnas = conteo["Azul"] + conteo["Verde"] + conteo["Rojo"]
    if ventanas_diurnas > 0:
        eficiencia = round((conteo["Verde"] / ventanas_diurnas) * 100, 2)
        proporciones = {
            "Azul": round((conteo["Azul"] / ventanas_diurnas) * 100, 2),
            "Verde": round((conteo["Verde"] / ventanas_diurnas) * 100, 2),
            "Rojo": round((conteo["Rojo"] / ventanas_diurnas) * 100, 2),
        }
    else:
        eficiencia = 0.0
        proporciones = {"Azul": 0.0, "Verde": 0.0, "Rojo": 0.0}

    return {
        "nombre": "Índice de Eficiencia Fotosintética Diaria",
        "eficiencia_fotosintetica": eficiencia,
        "ventanas_diurnas": ventanas_diurnas,
        "ventanas_totales": len(valores),
        "conteo_estados": conteo,
        "proporciones_diurnas_pct": proporciones,
    }

def despachar_historial_hoy(dt_actual):
    global buffer_lum_30m, ventana_30m_actual
    fecha_hoy = dt_actual.strftime("%Y-%m-%d")
    datos = leer_historial_generico(ARCHIVO_HISTORICO, fecha_hoy, "Luminosidad")
    
    if buffer_lum_30m and ventana_30m_actual:
        hora_corta = ventana_30m_actual.strftime("%H:%M")
        promedio_vivo = calcular_promedio(buffer_lum_30m)
        datos[hora_corta] = round(promedio_vivo, 2)

    kpi = calcular_kpi_eficiencia_fotosintetica(list(datos.values()))
    payload = {"fecha": fecha_hoy, "serie": datos, "kpi": kpi}
    cliente_rabbit.publish(TOPICOS_SALIDA["lum_historial"], json.dumps(payload), qos=1)

# ==========================================================
# CÁLCULOS DEL SENSOR DE SUELO & TASA DE SECADO
# ==========================================================
def clasificar_suelo(h):
    if h >= SATURACION:
        return "Azul|Suelo saturado y sin oxígeno.|Peligro de pudrición; no regar."
    if h >= CAPACIDAD_CAMPO:
        return "Verde|Rango óptimo para raíces.|Capacidad de Campo."
    if h >= PUNTO_MARCHITEZ:
        return "Amarillo|El suelo se está secando.|Estrés Leve. Monitorear riego."
    return "Rojo|Condición crítica.|Punto de Marchitez. Regar inmediatamente."

def calcular_tasa_secado():
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
    pendiente = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if abs(pendiente * SPAN_TASA_SEG) < UMBRAL_CAMBIO_PTS:
        return 0.0
    return -pendiente * 3600.0  # Devuelve la tasa expresada en % por hora

def estimar_tiempo_marchitez(prom, tasa):
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
    demanda_alta = dpv is not None and dpv >= DPV_DEMANDA_ALTA
    if prom <= PUNTO_MARCHITEZ:
        return "Rojo", "Suelo en punto de marchitez. Regar de inmediato."
    if horas is not None and horas <= ETA_CRITICA_H and demanda_alta:
        return "Rojo", "Se seca rápido y el aire está muy seco (DPV alto). Regar ya."
    if horas is not None and horas <= ETA_ALERTA_H:
        return "Amarillo", "Tendencia de secado constante. Programar riego."
    if demanda_alta and prom < CAPACIDAD_CAMPO:
        return "Amarillo", "Suelo algo seco y demanda atmosférica elevada."
    return None, None

def estado_suelo_final(prom, horas, dpv):
    color, diag, accion = clasificar_suelo(prom).split("|")
    rangos = {"Verde": 0, "Amarillo": 1, "Rojo": 2}
    r_color, r_msg = evaluar_riesgo_cruzado(prom, horas, dpv)
    if r_color and color in rangos and rangos[r_color] >= rangos[color]:
        color, diag, accion = r_color, "Riesgo por tendencia de secado y DPV.", r_msg
    return f"{color}|{diag}|{accion}"

def cerrar_ventana_suelo(ventana):
    global buffer_suelo
    if not buffer_suelo:
        return
    prom = calcular_promedio(buffer_suelo)
    buffer_suelo.clear()

    # Si hubo un salto brusco hacia arriba (riego/lluvia), se reinicia el historial de tasa
    if muestras_tasa and prom - muestras_tasa[-1][1] >= SALTO_RIEGO_PTS:
        muestras_tasa.clear()
    muestras_tasa.append((ventana, prom))
    
    while (ventana - muestras_tasa[0][0]).total_seconds() > SPAN_TASA_SEG:
        muestras_tasa.popleft()

    tasa = calcular_tasa_secado()
    txt_eta, horas = estimar_tiempo_marchitez(prom, tasa)

    print(f"[SUELO] Ventana {ventana.strftime('%H:%M:%S')}: {prom:.2f}% | "
          f"tasa={None if tasa is None else round(tasa, 2)} %/h | marchitez: {txt_eta}")

    r_color, r_msg = evaluar_riesgo_cruzado(prom, horas, ultimo_dpv)
    if r_color is None:
        msg_demanda = "Gris|Esperando datos atmosféricos (DPV)..." if ultimo_dpv is None else "Verde|Condiciones atmosféricas y de suelo estables."
    else:
        msg_demanda = f"{r_color}|{r_msg}"

    # Publicaciones MQTT hacia la capa web
    cliente_rabbit.publish(TOPICOS_SALIDA["hum_suelo_prom"], str(round(prom, 2)), qos=1)
    cliente_rabbit.publish(TOPICOS_SALIDA["hum_suelo_estado"], estado_suelo_final(prom, horas, ultimo_dpv), qos=1)
    cliente_rabbit.publish(TOPICOS_SALIDA["demanda_cruzada"], msg_demanda, qos=1)
    
    if tasa is not None:
        cliente_rabbit.publish(TOPICOS_SALIDA["tasa_secado"], str(round(tasa, 2)), qos=1)
    cliente_rabbit.publish(TOPICOS_SALIDA["tiempo_marchitez"], txt_eta, qos=1)

def formato_hora_suelo(hora):
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
    if not valores: return {}
    optimos = sum(1 for v in valores if CAPACIDAD_CAMPO <= v < SATURACION)
    riegos = sum(1 for a, b in zip(valores, valores[1:]) if b - a >= SALTO_RIEGO_PTS)
    return {
        "promedio": round(calcular_promedio(valores), 1),
        "min": round(min(valores), 1),
        "max": round(max(valores), 1),
        "pct_optimo": round(100 * optimos / len(valores)),
        "riegos": riegos
    }

def despachar_historial_suelo(dt_actual):
    serie = leer_historial_suelo(dt_actual.strftime("%Y-%m-%d"))
    payload = {"serie": serie, "resumen": calcular_resumen_suelo(list(serie.values()))}
    cliente_rabbit.publish(TOPICOS_SALIDA["hum_suelo_historial"], json.dumps(payload), qos=1)

def registrar_historico_suelo(cliente, ventana, valores):
    if not valores: return
    prom = calcular_promedio(valores)
    with open(ARCHIVO_HISTORICO_SUELO, mode='a', newline='') as file:
        csv.writer(file).writerow([ventana.strftime("%Y-%m-%d"), ventana.strftime("%H:%M:%S"), round(prom, 2)])
    print(f"[EDGE] Histórico de suelo guardado ({ventana.strftime('%H:%M:%S')}): {round(prom, 2)}%")
    despachar_historial_suelo(ventana)

def manejar_suelo(cliente, dt_mensaje, valor):
    global ventana_suelo_actual, ventana_suelo_hist_actual
    ventana = obtener_ventana_seg(dt_mensaje, VENTANA_SUELO_SEG)
    if ventana_suelo_actual is None:
        ventana_suelo_actual = ventana
    if ventana > ventana_suelo_actual:
        cerrar_ventana_suelo(ventana_suelo_actual)
        ventana_suelo_actual = ventana
    buffer_suelo.append(valor)

    ventana_h = obtener_ventana_seg(dt_mensaje, VENTANA_HIST_SUELO_SEG)
    if ventana_suelo_hist_actual is None:
        ventana_suelo_hist_actual = ventana_h
    if ventana_h > ventana_suelo_hist_actual:
        registrar_historico_suelo(cliente, ventana_suelo_hist_actual, buffer_suelo_hist)
        buffer_suelo_hist.clear()
        ventana_suelo_hist_actual = ventana_h
    buffer_suelo_hist.append(valor)

# ==========================================================
# GESTOR MQTT Y PROCESAMIENTO PRINCIPAL
# ==========================================================
def on_connect(cliente, userdata, flags, reason_code, properties=None):
    print(f"Edge conectado al broker MQTT con código: {reason_code}")
    cliente.subscribe(TOPICOS_ENTRADA)

def on_connect_rmq(cliente, userdata, flags, reason_code, properties=None):
    print(f"Edge conectado a RabbitMQ con código {reason_code}")
    cliente.subscribe((TOPICO_REQUEST_HISTORIAL, 1))
    print("Edge suscrito a historial")

def on_message(cliente, userdata, message):
    global buffers, ventana_actual, ventana_gdd_actual, buffer_lum_30m, ventana_30m_actual, ultimo_despacho_grafica, gdd_acumulado_anterior
    
    payload = message.payload.decode('utf-8')
    topico = message.topic
    
    # Peticiones de Historial (Dashboard recién conectado)
    if topico == TOPICO_REQUEST_HISTORIAL:
        print("\n[REQUEST] Despachando historial completo al Dashboard Web...")
        ahora = datetime.now()
        despachar_historial_hoy(ahora)
        despachar_historial_suelo(ahora)
        despachar_historial_gdd_diario()
        return

    # Lectura del payload (Fecha/Hora + Valor)
    try:
        str_fecha = payload[:19]
        str_valor = payload[19:].strip()
        dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
        valor = float(str_valor)
    except ValueError:
        return

    # Sensor de Suelo
    if topico == TOPICO_SUELO:
        if message.retain: return
        manejar_suelo(cliente, dt_mensaje, valor)
        return

    # Sensor de Iluminación
    if topico == "campo1/invernaderos/invernadero1/luminosidad":
        if valor <= 20: estado_lum = "Gris|Fotosíntesis mínima o nula.|Condición normal de noche. Si ocurre de día, revisar iluminación."
        elif valor <= 50: estado_lum = "Azul|Luz baja.|Retirar mallas sombra si están desplegadas."
        elif valor <= 85: estado_lum = "Verde|Rango ideal.|Condiciones ideales, no se requiere acción."
        else: estado_lum = "Rojo|Radiación extrema.|Desplegar malla sombra al 30% o 50% inmediatamente."

        cliente_rabbit.publish(TOPICOS_SALIDA["lum_prom"], str(round(valor, 2)), qos=1)
        cliente_rabbit.publish(TOPICOS_SALIDA["lum_estado"], estado_lum, qos=1)
        
        ventana_30m = obtener_ventana_minutos(dt_mensaje, 30)
        if ventana_30m_actual is None:
            ventana_30m_actual = ventana_30m

        if ventana_30m > ventana_30m_actual:
            prom_30m = calcular_promedio(buffer_lum_30m)
            fecha_str = ventana_30m_actual.strftime("%Y-%m-%d")
            hora_str = ventana_30m_actual.strftime("%H:%M:%S")
            
            with open(ARCHIVO_HISTORICO, mode='a', newline='') as file:
                csv.writer(file).writerow([fecha_str, hora_str, round(prom_30m, 2)])
            
            buffer_lum_30m.clear()
            ventana_30m_actual = ventana_30m
            despachar_historial_hoy(dt_mensaje)
            ultimo_despacho_grafica = dt_mensaje

        buffer_lum_30m.append(valor)
        if ultimo_despacho_grafica is None or (dt_mensaje - ultimo_despacho_grafica).total_seconds() >= 30:
            despachar_historial_hoy(dt_mensaje)
            ultimo_despacho_grafica = dt_mensaje
        return

    # Clima (Temperatura y Humedad Aire)
    ventana_mensaje = obtener_ventana_seg(dt_mensaje, VENTANA_CLIMA_SEG)
    ventana_gdd_mensaje = obtener_ventana_seg(dt_mensaje, VENTANA_GDD_SEG)
    
    if ventana_actual is None: ventana_actual = ventana_mensaje
    if ventana_gdd_actual is None: ventana_gdd_actual = ventana_gdd_mensaje

    if ventana_mensaje > ventana_actual:
        procesar_y_publicar_clima(ventana_actual)
        ventana_actual = ventana_mensaje
        
    # Bloque de GDD modificado dentro de on_message
    if ventana_gdd_mensaje > ventana_gdd_actual:
        # Calcular cuánto GDD se generó en esta ventana específica
        gdd_generado_ventana = max(0, gdd_acumulado - gdd_acumulado_anterior)
        
        # Guardar en histórico
        fecha_str = ventana_gdd_actual.strftime("%Y-%m-%d")
        with open(ARCHIVO_HISTORICO_GDD, mode='a', newline='') as file:
            # Se guarda la fecha, el GDD de la ventana, y el acumulado total
            csv.writer(file).writerow([fecha_str, round(gdd_generado_ventana, 4), round(gdd_acumulado, 2)])
        
        # Obtener etapa y preparar JSON
        etapa_actual = obtener_etapa_fenologica(gdd_acumulado)
        payload_gdd = {
            "gdd_acumulado": round(gdd_acumulado, 2),
            "etapa_crecimiento": etapa_actual
        }
        
        cliente_rabbit.publish(TOPICOS_SALIDA["gdd"], json.dumps(payload_gdd), qos=1)
        print(f"[EDGE] GDD publicado: {round(gdd_acumulado, 2)} | Etapa: {etapa_actual['nombre']}")
        
        # Prepararnos para la siguiente ventana
        gdd_acumulado_anterior = gdd_acumulado
        ventana_gdd_actual = ventana_gdd_mensaje

    if topico in buffers:
        buffers[topico].append(valor)

def on_message_rmq(cliente, userdata, message):
    topico = message.topic
    
    # Peticiones de Historial (Dashboard recién conectado)
    if topico == TOPICO_REQUEST_HISTORIAL:
        print("\n[REQUEST] Despachando historial completo al Dashboard Web...")
        ahora = datetime.now()
        despachar_historial_hoy(ahora)
        despachar_historial_suelo(ahora)
        despachar_historial_gdd_diario()
        return

def procesar_y_publicar_clima(ventana):
    global buffers, gdd_acumulado, ultimo_dpv
    print(f"\n--- CIERRE DE VENTANA CLIMA EDGE ({VENTANA_CLIMA_SEG} s): {ventana.strftime('%H:%M:%S')} ---")
    
    prom_temp = calcular_promedio(buffers["campo1/parcelas/maiz1/temperatura/centigrados"])
    prom_hum_aire = calcular_promedio(buffers["campo1/parcelas/maiz1/humedad/aire"])
    print(f"Temperatura promedio: {prom_temp}")
    print(f"Humedad del aire promedio: {prom_hum_aire}")
    
    fecha_str = ventana.strftime("%Y-%m-%d")
    hora_str = ventana.strftime("%H:%M:%S")

    # Guardar en CSV solo si hubo datos
    if buffers["campo1/parcelas/maiz1/temperatura/centigrados"]:
        with open(ARCHIVO_HISTORICO_TEMP, mode='a', newline='') as file:
            csv.writer(file).writerow([fecha_str, hora_str, round(prom_temp, 2)])
    
    if buffers["campo1/parcelas/maiz1/humedad/aire"]:
        with open(ARCHIVO_HISTORICO_HUM_AIRE, mode='a', newline='') as file:
            csv.writer(file).writerow([fecha_str, hora_str, round(prom_hum_aire, 2)])
    
    if prom_temp > 0 and prom_hum_aire > 0:
        dpv = temperatura_metricas.calcular_dpv(prom_temp, prom_hum_aire)
        dpd = temperatura_metricas.calcular_dpd(prom_temp, prom_hum_aire)
        print(f"Depresión de vapor: {dpv}")
        print(f"Déficit de punto de rocío: {dpd}")
        try:
            ultimo_dpv = float(dpv)
        except (TypeError, ValueError):
            pass
    else:
        dpv = dpd = 0.0

    gd = temperatura_metricas.calcular_gdh(prom_temp)
    gdd_acumulado += gd * VENTANA_CLIMA_SEG / 86400.0

    cliente.publish(TOPICOS_SALIDA["temp_prom"], str(round(prom_temp, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["hum_aire_prom"], str(round(prom_hum_aire, 2)), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpv"], str(dpv), qos=1)
    cliente.publish(TOPICOS_SALIDA["dpd"], str(dpd), qos=1)
    
    for key in buffers:
        buffers[key].clear()

def despachar_historial_gdd_diario():
    if not os.path.exists(ARCHIVO_HISTORICO_GDD):
        return
        
    historial_diario = {}
    with open(ARCHIVO_HISTORICO_GDD, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            fecha = row["Fecha"]
            # Al actualizar la clave repetidamente, nos quedamos con la última muestra del día
            historial_diario[fecha] = float(row["GDD_Acumulado"])
            
    # Formatear la lista de objetos para el dashboard
    serie_gdd = [{"fecha": f, "gdd_acumulado": v} for f, v in historial_diario.items()]
    
    # Publicar hacia el backend/dashboard
    cliente_rabbit.publish(TOPICOS_SALIDA["gdd_historial_diario"], json.dumps(serie_gdd), qos=1)
    print(f"[REQUEST] Historial diario de GDD despachado ({len(serie_gdd)} días).")

inicializar_csv()

# Cliente de RabbitMQ
cliente_rabbit = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
cliente_rabbit.on_connect = on_connect_rmq
cliente_rabbit.on_message = on_message_rmq
try:
    cliente_rabbit.connect(host=urlRabbitMQ, port=puertoRabbitMQ)
    cliente_rabbit.loop_start()
except Exception as e:
    print(f"Error conectando a RabbitMQ: {e}")
    
# Cliente de Mosquitto (recibe datos de los sensores)
cliente = mqtt.Client(client_id=id_cliente, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
cliente.username_pw_set(username=mqtt_user, password=mqtt_password)
cliente.on_connect = on_connect
cliente.on_message = on_message

try:
    cliente.connect(host=urlServidor, port=puerto)
    cliente.loop_forever()
except Exception as e:
    print(f"Error conectando a Mosquitto: {e}")
    cliente_rabbit.loop_stop()
    cliente_rabbit.disconnect()
    cliente.disconnect()