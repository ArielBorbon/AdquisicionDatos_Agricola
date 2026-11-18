def clasificar_estado_luminosidad(valor: float) -> str:
    if valor <= 20: return "Gris"
    if valor <= 50: return "Azul"
    if valor <= 85: return "Verde"
    return "Rojo"