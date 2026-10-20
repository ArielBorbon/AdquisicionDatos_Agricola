import os
import sys
import csv
from datetime import datetime

raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
from edge.edge_meta_data import urlServidor, puerto

# Importaciones para la gráfica histórica
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

ID_CLIENTE = "dashboard-agricola-principal"
MQTT_USER = "usuario_dashboard"
MQTT_PASSWORD = "password_seguro_dash"
TOPICO_BASE_EDGE = "campo1/edge/#"

class DashboardAgricola:
    def __init__(self, root):
        self.root = root
        self.root.title("Dashboard de Monitoreo Agrícola IoT")
        # Se amplía la ventana para acomodar la gráfica en la parte inferior
        self.root.geometry("750x950")
        self.root.configure(padx=20, pady=20)
        
        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 11))
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabelframe.Label", font=("Arial", 12, "bold"), foreground="#2c3e50")
        
        titulo = ttk.Label(self.root, text="Panel de Control - Áreas Agrícolas", font=("Arial", 16, "bold"))
        titulo.pack(pady=(0, 10))
        
        # Variables de texto
        self.var_temp = tk.StringVar(value="Esperando datos...")
        self.var_hum_aire = tk.StringVar(value="Esperando datos...")
        self.var_dpv = tk.StringVar(value="Esperando datos...")
        self.var_dpd = tk.StringVar(value="Esperando datos...")
        self.var_gdd = tk.StringVar(value="Esperando datos...")
        self.var_hum_suelo = tk.StringVar(value="Esperando datos...")
        self.var_tasa_secado = tk.StringVar(value="Esperando datos...")
        self.var_luminosidad = tk.StringVar(value="Esperando datos...")
        
        # Archivo histórico CSV
        self.archivo_csv = "historico_luminosidad.csv"
        self.inicializar_csv()

        # Listas para almacenar datos en memoria para la gráfica (Máximo 20 puntos visibles)
        self.x_data = []
        self.y_data = []
        self.max_puntos_grafica = 20

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
        # ZONA 3 (Invernadero 1 - Iluminación y Gráfica)
        # ==========================================
        frame_inv = ttk.LabelFrame(self.root, text=" Invernadero: Invernadero 1 (Iluminación) ", padding=(10, 10))
        frame_inv.pack(fill="both", expand=True, pady=5)
        
        # Sub-frame superior para los indicadores
        frame_inv_top = ttk.Frame(frame_inv)
        frame_inv_top.pack(fill="x")

        ttk.Label(frame_inv_top, text="Luminosidad:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(frame_inv_top, textvariable=self.var_luminosidad, font=("Arial", 12, "bold"), foreground="#f39c12").grid(row=0, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv_top, text="Estrés:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.lbl_color_lum = tk.Label(frame_inv_top, text="Esperando...", width=15, font=("Arial", 10, "bold"), fg="white", bg="gray")
        self.lbl_color_lum.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv_top, text="Fisiología:").grid(row=2, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_fisio_lum = ttk.Label(frame_inv_top, text="...", wraplength=450)
        self.lbl_fisio_lum.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(frame_inv_top, text="Acción:").grid(row=3, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_accion_lum = ttk.Label(frame_inv_top, text="...", wraplength=450)
        self.lbl_accion_lum.grid(row=3, column=1, sticky="w", padx=5, pady=2)

        # Gráfica Histórica incrustada
        self.fig, self.ax = plt.subplots(figsize=(6, 2.5), dpi=100)
        self.fig.patch.set_facecolor('#f0f0f0')
        self.ax.set_title('Historial Reciente de Luminosidad (%)', fontsize=10)
        self.ax.set_ylim(0, 105)
        self.ax.tick_params(axis='x', rotation=45, labelsize=8)
        self.linea_grafica, = self.ax.plot([], [], marker='o', color='#f39c12', linewidth=2)
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=frame_inv)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, pady=10)

        self.configurar_mqtt()

    def inicializar_csv(self):
        """Crea el archivo CSV con encabezados si no existe."""
        if not os.path.exists(self.archivo_csv):
            with open(self.archivo_csv, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Fecha", "Hora", "Luminosidad_Porcentaje"])

    def registrar_y_graficar(self, valor):
        """Guarda en CSV y actualiza la gráfica. Se ejecuta en el hilo principal."""
        ahora = datetime.now()
        fecha_str = ahora.strftime("%Y-%m-%d")
        hora_str = ahora.strftime("%H:%M:%S")

        # 1. Guardar histórico en CSV
        with open(self.archivo_csv, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([fecha_str, hora_str, valor])

        # 2. Actualizar datos en memoria para la gráfica
        self.x_data.append(hora_str)
        self.y_data.append(valor)

        # Mantener solo los últimos N puntos para evitar saturar la gráfica visual
        if len(self.x_data) > self.max_puntos_grafica:
            self.x_data.pop(0)
            self.y_data.pop(0)

        # 3. Redibujar la gráfica
        self.linea_grafica.set_data(range(len(self.x_data)), self.y_data)
        self.ax.set_xticks(range(len(self.x_data)))
        self.ax.set_xticklabels(self.x_data)
        self.ax.set_xlim(0, max(1, len(self.x_data) - 1))
        self.canvas.draw()

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
        
        colores_hex = {
            "Gris": "#7f8c8d", "Azul": "#2980b9",
            "Verde": "#27ae60", "Amarillo": "#f1c40f", "Rojo": "#c0392b"
        }

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

        elif "invernadero1/luminosidad/promedio" in topico:
            self.var_luminosidad.set(f"{payload} %")
            try:
                valor_float = float(payload)
                # Delegar la actualización gráfica y el guardado al hilo principal de Tkinter
                self.root.after(0, self.registrar_y_graficar, valor_float)
            except ValueError:
                pass

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
        self.root.quit()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = DashboardAgricola(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()