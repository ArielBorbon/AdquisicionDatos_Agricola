import os
import sys

# Encuentra de forma automática la carpeta raíz 'AdquisicionDatos_Agricola'
raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

# Ahora sí, importa buscando desde la raíz del proyecto
import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
from edge.edge_meta_data import urlServidor, puerto  # <-- Nota el 'edge.' antes del archivo

# ==========================================
# CONFIGURACIÓN MQTT DEL DASHBOARD
# ==========================================
ID_CLIENTE = "dashboard-agricola-principal"
MQTT_USER = "usuario_dashboard"
MQTT_PASSWORD = "password_seguro_dash"

# Tópico base al que se suscribirá la capa de aplicación (Consumo exclusivo del Edge)
TOPICO_BASE_EDGE = "campo1/edge/#"

class DashboardAgricola:
    def __init__(self, root):
        self.root = root
        self.root.title("Dashboard de Monitoreo Agrícola IoT")
        self.root.geometry("600x450")
        self.root.configure(padx=20, pady=20)
        
        # Estilos
        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 12))
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabelframe.Label", font=("Arial", 12, "bold"), foreground="#2c3e50")
        
        # Título principal
        titulo = ttk.Label(self.root, text="Panel de Control - Áreas Agrícolas", font=("Arial", 16, "bold"))
        titulo.pack(pady=(0, 20))
        
        # ==========================================
        # VARIABLES DINÁMICAS (StringVars)
        # ==========================================
        self.var_temp = tk.StringVar(value="Esperando datos...")
        self.var_hum_aire = tk.StringVar(value="Esperando datos...")
        self.var_dpv = tk.StringVar(value="Esperando datos...")
        self.var_dpd = tk.StringVar(value="Esperando datos...")
        self.var_hum_suelo = tk.StringVar(value="Esperando datos...")
        self.var_luminosidad = tk.StringVar(value="Esperando datos...")
        
        # ==========================================
        # INTERFAZ: ZONA 1 (Parcela Maíz 1 - Clima)
        # ==========================================
        frame_maiz = ttk.LabelFrame(self.root, text=" Parcela: Maíz 1 (Condiciones Climáticas) ", padding=(10, 10))
        frame_maiz.pack(fill="x", pady=10)
        
        ttk.Label(frame_maiz, text="Temperatura Promedio:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_temp, font=("Arial", 12, "bold"), foreground="#c0392b").grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(frame_maiz, text="Humedad Relativa Promedio:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_hum_aire, font=("Arial", 12, "bold"), foreground="#2980b9").grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_maiz, text="Déficit de Presión de Vapor (DPV):").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_dpv, font=("Arial", 12, "bold")).grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(frame_maiz, text="Depresión del Punto de Rocío (DPD):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_dpd, font=("Arial", 12, "bold")).grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # ==========================================
        # INTERFAZ: ZONA 2 (Parcela 1 - Suelo)
        # ==========================================
        frame_suelo = ttk.LabelFrame(self.root, text=" Parcela: Parcela 1 (Condiciones de Suelo) ", padding=(10, 10))
        frame_suelo.pack(fill="x", pady=10)
        
        ttk.Label(frame_suelo, text="Humedad de Suelo Promedio:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_suelo, textvariable=self.var_hum_suelo, font=("Arial", 12, "bold"), foreground="#8e44ad").grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # ==========================================
        # INTERFAZ: ZONA 3 (Invernadero 1 - Iluminación)
        # ==========================================
        frame_inv = ttk.LabelFrame(self.root, text=" Invernadero: Invernadero 1 (Iluminación) ", padding=(10, 10))
        frame_inv.pack(fill="x", pady=10)
        
        ttk.Label(frame_inv, text="Luminosidad Promedio:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_inv, textvariable=self.var_luminosidad, font=("Arial", 12, "bold"), foreground="#f39c12").grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # ==========================================
        # INICIALIZACIÓN MQTT
        # ==========================================
        self.configurar_mqtt()

    def configurar_mqtt(self):
        self.cliente_mqtt = mqtt.Client(client_id=ID_CLIENTE, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.cliente_mqtt.username_pw_set(username=MQTT_USER, password=MQTT_PASSWORD)
        
        self.cliente_mqtt.on_connect = self.on_connect
        self.cliente_mqtt.on_message = self.on_message
        
        print("Conectando Dashboard al Broker MQTT...")
        self.cliente_mqtt.connect(host=urlServidor, port=puerto)
        
        # Inicia el hilo secundario para procesar red sin bloquear la interfaz gráfica
        self.cliente_mqtt.loop_start()

    def on_connect(self, cliente, userdata, flags, reason_code, properties=None):
        print(f"Dashboard conectado con código: {reason_code}")
        # Suscripción exclusiva a la capa Edge (QoS 2 ideal para Dashboard si el broker y script lo permiten, usaremos QoS 1 base)
        cliente.subscribe(TOPICO_BASE_EDGE, qos=1)

    def on_message(self, cliente, userdata, message):
        topico = message.topic
        payload = message.payload.decode('utf-8')
        
        # Mapeo de tópicos hacia las variables dinámicas de la interfaz
        # (El método .set() de StringVar actualiza la ventana automáticamente)
        if "maiz1/temperatura/promedio" in topico:
            self.var_temp.set(f"{payload} °C")
        elif "maiz1/humedad_aire/promedio" in topico:
            self.var_hum_aire.set(f"{payload} %")
        elif "maiz1/dpv" in topico:
            self.var_dpv.set(f"{payload} kPa")
        elif "maiz1/dpd" in topico:
            self.var_dpd.set(f"{payload} °C")
        elif "parcela1/humedad_suelo/promedio" in topico:
            self.var_hum_suelo.set(f"{payload} %")
        elif "invernadero1/luminosidad/promedio" in topico:
            self.var_luminosidad.set(f"{payload} %")

    def on_closing(self):
        """Detiene el cliente MQTT limpiamente antes de cerrar la ventana"""
        self.cliente_mqtt.loop_stop()
        self.cliente_mqtt.disconnect()
        self.root.destroy()

# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == "__main__":
    root = tk.Tk()
    app = DashboardAgricola(root)
    
    # Maneja el evento de cerrar la ventana (la 'X' roja)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Bucle principal de la interfaz gráfica
    root.mainloop()