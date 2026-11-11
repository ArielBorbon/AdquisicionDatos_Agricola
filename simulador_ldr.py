"""Simulador del nodo ESP32 de iluminación (LDR) para pruebas en seco con RabbitMQ."""

from datetime import datetime
import random
import time
import paho.mqtt.client as mqtt  # type: ignore

BROKER_HOST = "localhost"
BROKER_PORT = 1883
CLIENT_ID = "esp32-luminosidad-simulador"
MQTT_USER = "sensor_ldr_inv1"
MQTT_PASSWORD = "password_seguro_ldr"
TOPICO_LUMINOSIDAD = "campo1/invernaderos/invernadero1/luminosidad"
INTERVALO_SEG = 2


def on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[SIM-LDR] Conectado a RabbitMQ ({BROKER_HOST}:{BROKER_PORT}) | código={reason_code}")


def crear_cliente() -> mqtt.Client:
    kwargs = {"client_id": CLIENT_ID}
    if hasattr(mqtt, "CallbackAPIVersion"):
        kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
    client = mqtt.Client(**kwargs)
    client.username_pw_set(username=MQTT_USER, password=MQTT_PASSWORD)
    client.on_connect = on_connect
    return client


def main():
    client = crear_cliente()
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    print(f"[SIM-LDR] Publicando cada {INTERVALO_SEG}s en '{TOPICO_LUMINOSIDAD}' (Ctrl+C para detener)...")
    try:
        while True:
            fecha_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            valor_ldr = round(random.uniform(0.0, 100.0), 2)
            # Formato idéntico al ESP32 real: "DD/MM/YYYY HH:MM:SS <valor>"
            payload = f"{fecha_str} {valor_ldr:.2f}"

            info = client.publish(TOPICO_LUMINOSIDAD, payload, qos=1, retain=True)
            info.wait_for_publish(timeout=5)
            print(f"[SIM-LDR] Enviado -> {payload}%")
            time.sleep(INTERVALO_SEG)
    except KeyboardInterrupt:
        print("\n[SIM-LDR] Deteniendo simulador...")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

