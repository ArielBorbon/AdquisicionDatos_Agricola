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