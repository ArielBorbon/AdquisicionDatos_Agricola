# ---- Umbrales de Humedad del Suelo (% VWC) ----
from collections import deque


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

def clasificar_suelo(h):
    if h >= SATURACION:
        return "Azul|Suelo saturado y sin oxígeno.|Peligro de pudrición; no regar."
    if h >= CAPACIDAD_CAMPO:
        return "Verde|Rango óptimo para raíces.|Capacidad de Campo."
    if h >= PUNTO_MARCHITEZ:
        return "Amarillo|El suelo se está secando.|Estrés Leve. Monitorear riego."
    return "Rojo|Condición crítica.|Punto de Marchitez. Regar inmediatamente."

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