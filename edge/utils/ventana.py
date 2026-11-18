from datetime import datetime

def obtener_ventana_minutos(dt: datetime, minutos: int) -> datetime:
    minuto_redondeado = (dt.minute // minutos) * minutos
    return dt.replace(minute=minuto_redondeado, second=0, microsecond=0)

def obtener_ventana_seg(dt: datetime, segundos: int) -> datetime:
    seg_dia = dt.hour * 3600 + dt.minute * 60 + dt.second
    seg_dia -= seg_dia % segundos
    return dt.replace(hour=seg_dia // 3600, minute=(seg_dia % 3600) // 60,
                      second=seg_dia % 60, microsecond=0)