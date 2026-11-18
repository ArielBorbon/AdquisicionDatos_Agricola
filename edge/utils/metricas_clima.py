import math
import random

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

TEMP_BASE_MAIZ = 10.0

TEMP_MEDIA_MENSUAL = {
    1: 17.0, 2: 18.0, 3: 20.0, 4: 23.0,
    5: 27.0, 6: 30.0, 7: 31.0, 8: 31.0,
    9: 30.0, 10: 27.0, 11: 22.0, 12: 17.0
}

"""
Calcula el Déficit de Presión de Vapor (DPV) en kilopascales (kPa).
    :param temperatura: Temperatura ambiente en °C
    :param humedad: Humedad relativa en % (ej. 45.0)
    :return: Valor del DPV en kPa
"""
def calcular_dpv(temperatura: float, humedad: float) -> float:   
    # Paso A. Calcular la Presión de Vapor de Saturación (PVS) usando Tetens
    pvs = 0.61078 * math.exp((17.27 * temperatura) / (temperatura + 237.3))
    
    # Paso B. Calcular la Presión de Vapor Actual (PVA)
    pva = pvs * (humedad / 100.0)
    
    # Paso C. Obtener el DPV
    dpv = pvs - pva
    # Retorna el resultado redondeado a 3 decimales
    return round(dpv, 3)

"""
Calcula la Depresión del Punto de Rocío (DPD) en °C.
    :param temperatura: Temperatura ambiente en °C
    :param humedad: Humedad relativa en % (ej. 45.0)
    :return: Grados Celsius de diferencia hasta el rocío
"""
def calcular_dpd(temperatura: float, humedad: float) -> float:
    # Protección matemática: evitar logaritmo de cero si el sensor DHT11 falla y envía 0%
    if humedad <= 0:
        humedad = 0.001 
        
    # Paso A. Calcular la constante intermedia (gamma)
    gamma = ((17.27 * temperatura) / (237.3 + temperatura)) + math.log(humedad / 100.0)
    
    # Paso B. Calcular el Punto de Rocío (Td)
    punto_rocio = (237.3 * gamma) / (17.27 - gamma)
    
    # Paso C. Obtener la Depresión del Punto de Rocío (Brecha térmica)
    dpd = temperatura - punto_rocio
    
    return round(dpd, 2)

def calcular_gdh(temperatura: float) -> float:
    gdh = temperatura - TEMP_BASE_MAIZ
    return 0 if gdh < 0 else gdh

def obtener_etapa_fenologica(gdd_actual):
    for etapa in ETAPAS_MAIZ:
        if gdd_actual >= etapa["gdd"]:
            return {"nombre": etapa["nombre"], "descripcion": etapa["desc"]}
    return {"nombre": "Desconocida", "descripcion": "Sin datos."}

def gdd_random() -> int:
    return random.choice([
        random.randint(0, 65), random.randint(65, 150), random.randint(150, 235),
        random.randint(235, 340), random.randint(340, 450), random.randint(450, 650),
        random.randint(650, 750), random.randint(750, 850), random.randint(850, 1000),
        random.randint(1000, 1150), random.randint(1150, 1300), random.randint(1300, 1600)
    ])