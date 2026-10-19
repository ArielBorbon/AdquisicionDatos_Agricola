import os
import sys

raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
from edge.edge_meta_data import urlServidor, puerto

ID_CLIENTE = "dashboard-agricola-principal"
MQTT_USER = "usuario_dashboard"
MQTT_PASSWORD = "password_seguro_dash"
TOPICO_BASE_EDGE = "campo1/edge/#"

class DashboardAgricola:
    def __init__(self, root):
        self.root = root
        self.root.title("Dashboard de Monitoreo Agrícola IoT")
        # Se aumentó la altura de la ventana a 700 para acomodar las alertas de texto largas
        self.root.geometry("650x700")
        self.root.configure(padx=20, pady=20)
        
        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 11))
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabelframe.Label", font=("Arial", 12, "bold"), foreground="#2c3e50")
        
        titulo = ttk.Label(self.root, text="Panel de Control - Áreas Agrícolas", font=("Arial", 16, "bold"))
        titulo.pack(pady=(0, 20))
        
        self.var_temp = tk.StringVar(value="Esperando datos...")
        self.var_hum_aire = tk.StringVar(value="Esperando datos...")
        self.var_dpv = tk.StringVar(value="Esperando datos...")
        self.var_dpd = tk.StringVar(value="Esperando datos...")
        self.var_hum_suelo = tk.StringVar(value="Esperando datos...")
        self.var_luminosidad = tk.StringVar(value="Esperando datos...")
        
        # ZONA 1 (Maíz)
        frame_maiz = ttk.LabelFrame(self.root, text=" Parcela: Maíz 1 (Clima) ", padding=(10, 10))
        frame_maiz.pack(fill="x", pady=10)
        
        ttk.Label(frame_maiz, text="Temp Promedio:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_temp, font=("Arial", 12, "bold"), foreground="#c0392b").grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(frame_maiz, text="Hum Relativa Promedio:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_hum_aire, font=("Arial", 12, "bold"), foreground="#2980b9").grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_maiz, text="DPV:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_dpv, font=("Arial", 12, "bold")).grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(frame_maiz, text="DPD:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_dpd, font=("Arial", 12, "bold")).grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # ZONA 2 (Suelo)
        frame_suelo = ttk.LabelFrame(self.root, text=" Parcela: Parcela 1 (Suelo) ", padding=(10, 10))
        frame_suelo.pack(fill="x", pady=10)
        
        ttk.Label(frame_suelo, text="Humedad Promedio:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_suelo, textvariable=self.var_hum_suelo, font=("Arial", 12, "bold"), foreground="#8e44ad").grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # ZONA 3 (Iluminación con Semáforo)
        frame_inv = ttk.LabelFrame(self.root, text=" Invernadero: Invernadero 1 (Iluminación) ", padding=(10, 10))
        frame_inv.pack(fill="x", pady=10)
        
        ttk.Label(frame_inv, text="Luminosidad:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_inv, textvariable=self.var_luminosidad, font=("Arial", 12, "bold"), foreground="#f39c12").grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Elementos visuales del semáforo
        ttk.Label(frame_inv, text="Alerta:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.lbl_color = tk.Label(frame_inv, text="Esperando...", width=15, font=("Arial", 10, "bold"), fg="white", bg="gray")
        self.lbl_color.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv, text="Fisiología:").grid(row=2, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_fisio = ttk.Label(frame_inv, text="...", wraplength=450)
        self.lbl_fisio.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv, text="Acción:").grid(row=3, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_accion = ttk.Label(frame_inv, text="...", wraplength=450)
        self.lbl_accion.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        self.configurar_mqtt()

    def configurar_mqtt(self):
        self.cliente_mqtt = mqtt.Client(client_id=ID_CLIENTE, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.cliente_mqtt.username_pw_set(username=MQTT_USER, password=MQTT_PASSWORD)
        self.cliente_mqtt.on_connect = self.on_connect
        self.cliente_mqtt.on_message = self.on_message
        print("Conectando Dashboard al Broker MQTT...")
        self.cliente_mqtt.connect(host=urlServidor, port=puerto)
        self.cliente_mqtt.loop_start()

    def on_connect(self, cliente, userdata, flags, reason_code, properties=None):
        cliente.subscribe(TOPICO_BASE_EDGE, qos=1)

    def on_message(self, cliente, userdata, message):
        topico = message.topic
        payload = message.payload.decode('utf-8')
        
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
        elif "invernadero1/luminosidad/estado" in topico:
            # Separar el string usando el delimitador |
            datos = payload.split('|')
            if len(datos) == 3:
                color, fisio, accion = datos
                
                # Asignar código HEX según el color que envió el Edge
                colores_hex = {
                    "Gris": "#7f8c8d",
                    "Azul": "#2980b9",
                    "Verde": "#27ae60",
                    "Rojo": "#c0392b"
                }
                bg_color = colores_hex.get(color, "gray")
                
                # Actualizar la interfaz gráfica
                self.lbl_color.config(text=color.upper(), bg=bg_color)
                self.lbl_fisio.config(text=fisio)
                self.lbl_accion.config(text=accion)

    def on_closing(self):
        self.cliente_mqtt.loop_stop()
        self.cliente_mqtt.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = DashboardAgricola(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()