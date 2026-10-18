import math

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