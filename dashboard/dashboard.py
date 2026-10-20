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
        # Ajustamos la altura para hacer espacio a las nuevas métricas
        self.root.geometry("650x850")
        self.root.configure(padx=20, pady=20)
        
        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 11))
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabelframe.Label", font=("Arial", 12, "bold"), foreground="#2c3e50")
        
        titulo = ttk.Label(self.root, text="Panel de Control - Áreas Agrícolas", font=("Arial", 16, "bold"))
        titulo.pack(pady=(0, 10))
        
        # Variables de texto a actualizar
        self.var_temp = tk.StringVar(value="Esperando datos...")
        self.var_hum_aire = tk.StringVar(value="Esperando datos...")
        self.var_dpv = tk.StringVar(value="Esperando datos...")
        self.var_dpd = tk.StringVar(value="Esperando datos...")
        self.var_gdd = tk.StringVar(value="Esperando datos...")
        
        self.var_hum_suelo = tk.StringVar(value="Esperando datos...")
        self.var_tasa_secado = tk.StringVar(value="Esperando datos...")
        
        self.var_luminosidad = tk.StringVar(value="Esperando datos...")
        
        # ==========================================
        # ZONA 1 (Maíz - Clima)
        # ==========================================
        frame_maiz = ttk.LabelFrame(self.root, text=" Parcela: Maíz 1 (Clima) ", padding=(10, 10))
        frame_maiz.pack(fill="x", pady=5)
        
        ttk.Label(frame_maiz, text="Temp Promedio:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_temp, font=("Arial", 12, "bold"), foreground="#c0392b").grid(row=0, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(frame_maiz, text="Hum Relativa Promedio:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_hum_aire, font=("Arial", 12, "bold"), foreground="#2980b9").grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_maiz, text="DPV:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_dpv, font=("Arial", 12, "bold")).grid(row=2, column=1, sticky="w", padx=5, pady=2)
        
        ttk.Label(frame_maiz, text="DPD (Punto de Rocío):").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_dpd, font=("Arial", 12, "bold")).grid(row=3, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_maiz, text="GDD Acumulado:").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_maiz, textvariable=self.var_gdd, font=("Arial", 12, "bold")).grid(row=4, column=1, sticky="w", padx=5, pady=2)

        # ==========================================
        # ZONA 2 (Parcela 1 - Suelo)
        # ==========================================
        frame_suelo = ttk.LabelFrame(self.root, text=" Parcela: Parcela 1 (Humedad de Suelo) ", padding=(10, 10))
        frame_suelo.pack(fill="x", pady=5)
        
        ttk.Label(frame_suelo, text="Humedad Promedio:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_suelo, textvariable=self.var_hum_suelo, font=("Arial", 12, "bold"), foreground="#8e44ad").grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_suelo, text="Tasa de Secado:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_suelo, textvariable=self.var_tasa_secado, font=("Arial", 12, "bold")).grid(row=1, column=1, sticky="w", padx=5, pady=2)

        # Semáforo de Riego (Saturación Hídrica)
        ttk.Label(frame_suelo, text="Saturación:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.lbl_color_suelo = tk.Label(frame_suelo, text="Esperando...", width=15, font=("Arial", 10, "bold"), fg="white", bg="gray")
        self.lbl_color_suelo.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_suelo, text="Diagnóstico:").grid(row=3, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_diag_suelo = ttk.Label(frame_suelo, text="...", wraplength=450)
        self.lbl_diag_suelo.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_suelo, text="Acción:").grid(row=4, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_accion_suelo = ttk.Label(frame_suelo, text="...", wraplength=450)
        self.lbl_accion_suelo.grid(row=4, column=1, sticky="w", padx=5, pady=2)

        # ==========================================
        # ZONA 3 (Invernadero 1 - Iluminación)
        # ==========================================
        frame_inv = ttk.LabelFrame(self.root, text=" Invernadero: Invernadero 1 (Iluminación) ", padding=(10, 10))
        frame_inv.pack(fill="x", pady=5)
        
        ttk.Label(frame_inv, text="Luminosidad:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_inv, textvariable=self.var_luminosidad, font=("Arial", 12, "bold"), foreground="#f39c12").grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv, text="Estrés:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.lbl_color_lum = tk.Label(frame_inv, text="Esperando...", width=15, font=("Arial", 10, "bold"), fg="white", bg="gray")
        self.lbl_color_lum.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv, text="Fisiología:").grid(row=2, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_fisio_lum = ttk.Label(frame_inv, text="...", wraplength=450)
        self.lbl_fisio_lum.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv, text="Acción:").grid(row=3, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_accion_lum = ttk.Label(frame_inv, text="...", wraplength=450)
        self.lbl_accion_lum.grid(row=3, column=1, sticky="w", padx=5, pady=2)

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
        
        # Diccionario maestro de colores HEX
        colores_hex = {
            "Gris": "#7f8c8d",
            "Azul": "#2980b9",
            "Verde": "#27ae60",
            "Amarillo": "#f1c40f",
            "Rojo": "#c0392b"
        }

        # 1. Tópicos de Temperatura / Clima
        if "maiz1/temperatura/promedio" in topico:
            self.var_temp.set(f"{payload} °C")
        elif "maiz1/humedad_aire/promedio" in topico:
            self.var_hum_aire.set(f"{payload} %")
        elif "maiz1/dpv" in topico:
            self.var_dpv.set(f"{payload} kPa")
        elif "maiz1/dpd" in topico:
            self.var_dpd.set(f"{payload} °C")
        elif "maiz1/gdd" in topico:
            self.var_gdd.set(f"{payload} Días Grado")
            
        # 2. Tópicos de Humedad de Suelo
        elif "parcela1/humedad_suelo/promedio" in topico:
            self.var_hum_suelo.set(f"{payload} %")
        elif "parcela1/humedad_suelo/tasa_secado" in topico:
            self.var_tasa_secado.set(f"{payload} % / hora")
        elif "parcela1/humedad_suelo/estado" in topico:
            datos = payload.split('|')
            if len(datos) == 3:
                color, diag, accion = datos
                bg_color = colores_hex.get(color, "gray")
                self.lbl_color_suelo.config(text=color.upper(), bg=bg_color)
                self.lbl_diag_suelo.config(text=diag)
                self.lbl_accion_suelo.config(text=accion)

        # 3. Tópicos de Iluminación
        elif "invernadero1/luminosidad/promedio" in topico:
            self.var_luminosidad.set(f"{payload} %")
        elif "invernadero1/luminosidad/estado" in topico:
            datos = payload.split('|')
            if len(datos) == 3:
                color, fisio, accion = datos
                bg_color = colores_hex.get(color, "gray")
                self.lbl_color_lum.config(text=color.upper(), bg=bg_color)
                self.lbl_fisio_lum.config(text=fisio)
                self.lbl_accion_lum.config(text=accion)

    def on_closing(self):
        self.cliente_mqtt.loop_stop()
        self.cliente_mqtt.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = DashboardAgricola(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
