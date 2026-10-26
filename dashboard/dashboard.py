import os
import sys
import json
import queue
import numpy as np
from datetime import datetime

raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

import tkinter as tk
from tkinter import Tk, ttk
import tkinter.font as tkfont
import paho.mqtt.client as mqtt
from edge.edge_meta_data import urlServidor, puerto

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

ID_CLIENTE = "dashboard-agricola-principal"
MQTT_USER = "usuario_dashboard"
MQTT_PASSWORD = "password_seguro_dash"
TOPICO_BASE_EDGE = "campo1/#"

ANCHO_BASE = 1500
ALTO_BASE = 700

MARGENES_GRAFICA = dict(left=0.11, right=0.97, top=0.88, bottom=0.22)
PUNTOS_VISIBLES_SUELO = 12

class DashboardAgricola:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Dashboard de Monitoreo Agrícola IoT")
        self.root.geometry(f"{ANCHO_BASE}x{ALTO_BASE}")
        self.root.minsize(900, 520)
        self.root.configure(padx=20, pady=20)

        self.cola_mensajes = queue.Queue()

        self.tamanos_base = {"normal": 11, "valor": 12, "titulo": 16, "nota": 8, "badge": 10, "card": 12}
        self.fuentes = {
            "normal": tkfont.Font(family="Arial", size=11),
            "valor": tkfont.Font(family="Arial", size=12, weight="bold"),
            "titulo": tkfont.Font(family="Arial", size=16, weight="bold"),
            "nota": tkfont.Font(family="Arial", size=8, slant="italic"),
            "badge": tkfont.Font(family="Arial", size=10, weight="bold"),
            "card": tkfont.Font(family="Arial", size=12, weight="bold"),
        }
        self.f_normal = self.fuentes["normal"]
        self.f_valor = self.fuentes["valor"]
        self.f_titulo = self.fuentes["titulo"]
        self.f_nota = self.fuentes["nota"]
        self.f_badge = self.fuentes["badge"]
        self.f_card = self.fuentes["card"]
        self.escala = 1.0

        style = ttk.Style()
        style.configure("TLabel", font=self.f_normal)
        style.configure("TFrame", background="#f0f0f0")
        style.configure("TLabelframe.Label", font=self.f_card, foreground="#2c3e50")

        titulo = ttk.Label(self.root, text="Panel de Control - Áreas Agrícolas", font=self.f_titulo)
        titulo.pack(pady=(0, 10))

        self.var_temp = tk.StringVar(value="Esperando datos...")
        self.var_hum_aire = tk.StringVar(value="Esperando datos...")
        self.var_dpv = tk.StringVar(value="Esperando datos...")
        self.var_dpd = tk.StringVar(value="Esperando datos...")
        self.var_gdd = tk.StringVar(value="Esperando datos...")
        self.var_hum_suelo = tk.StringVar(value="Esperando datos...")
        self.var_tasa_secado = tk.StringVar(value="Esperando datos...")
        self.var_tiempo_marchitez = tk.StringVar(value="Esperando datos...")
        self.var_resumen_suelo = tk.StringVar(value="Esperando histórico...")
        self.var_luminosidad = tk.StringVar(value="Esperando datos...")

        self.tarjetas = []
        self.infos = []
        self.graficas = []
        self._wrap_items = []
        self._job_resize = None
        self._ultimo_tam = None
        self._altura_info = None

        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(0, weight=1)
        for col in range(3):
            main_frame.columnconfigure(col, weight=1, uniform="tarjetas")

        # ==========================================
        # TARJETA 1: Maíz (Clima)
        # ==========================================
        frame_maiz, info_maiz = self._crear_tarjeta(main_frame, 0, " Parcela: Maíz 1 (Clima) ", (0, 8))

        self._fila(info_maiz, 0, "Temp Promedio:", self.var_temp, "#c0392b")
        self._fila(info_maiz, 1, "Hum Relativa Promedio:", self.var_hum_aire, "#2980b9")

        # DPD Modificado
        ttk.Label(info_maiz, text="DPD:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        frame_dpd = ttk.Frame(info_maiz)
        frame_dpd.grid(row=2, column=1, sticky="w")
        ttk.Label(frame_dpd, textvariable=self.var_dpd, font=self.f_valor).pack(side="left")
        self.lbl_color_dpd = tk.Label(frame_dpd, text="Esperando...", width=12, font=self.f_badge, fg="white", bg="gray")
        self.lbl_color_dpd.pack(side="left", padx=5)

        ttk.Label(info_maiz, text="Patógenos:").grid(row=3, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_dpd_pat = ttk.Label(info_maiz, text="...", wraplength=220)
        self.lbl_dpd_pat.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_dpd_pat, info_maiz, "col1"))

        ttk.Label(info_maiz, text="Agroquímicos:").grid(row=4, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_dpd_agro = ttk.Label(info_maiz, text="...", wraplength=220)
        self.lbl_dpd_agro.grid(row=4, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_dpd_agro, info_maiz, "col1"))

        # GDD Modificado
        self._fila(info_maiz, 5, "GDD Acumulado:", self.var_gdd, "#27ae60")
        ttk.Label(info_maiz, text="Etapa:").grid(row=6, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_gdd_etapa = ttk.Label(info_maiz, text="...", wraplength=220, font=self.f_badge)
        self.lbl_gdd_etapa.grid(row=6, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_gdd_etapa, info_maiz, "col1"))

        ttk.Label(info_maiz, text="Hito:").grid(row=7, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_gdd_hito = ttk.Label(info_maiz, text="...", wraplength=220)
        self.lbl_gdd_hito.grid(row=7, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_gdd_hito, info_maiz, "col1"))

        # DPV: Tacómetro
        self.fig_dpv, self.ax_dpv, self.canvas_dpv = self._crear_grafica_tacometro(frame_maiz, "Déficit de Presión de Vapor (DPV) - kPa")
        self.lbl_dpv_msg = ttk.Label(frame_maiz, text="Esperando datos...", anchor="center", justify="center", wraplength=350, font=self.f_normal)
        self.lbl_dpv_msg.grid(row=2, column=0, pady=5)

        # ==========================================
        # TARJETA 2: Invernadero (Iluminación)
        # ==========================================
        frame_inv, info_inv = self._crear_tarjeta(main_frame, 1, " Invernadero: Invernadero 1 (Iluminación) ", (8, 8))

        self._fila(info_inv, 0, "Nivel Actual (Live):", self.var_luminosidad, "#f39c12")
        ttk.Label(info_inv, text="Estrés:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.lbl_color_lum = tk.Label(info_inv, text="Esperando...", width=15, font=self.f_badge, fg="white", bg="gray")
        self.lbl_color_lum.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        ttk.Label(info_inv, text="Fisiología:").grid(row=2, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_fisio_lum = ttk.Label(info_inv, text="...", wraplength=300)
        self.lbl_fisio_lum.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_fisio_lum, info_inv, "col1"))

        ttk.Label(info_inv, text="Acción:").grid(row=3, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_accion_lum = ttk.Label(info_inv, text="...", wraplength=300)
        self.lbl_accion_lum.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_accion_lum, info_inv, "col1"))

        self.fig, self.ax, self.canvas = self._crear_grafica(
            frame_inv, "Tendencia Diaria de Luminosidad Promedio (Cada 30m)")
        self.linea_grafica, = self.ax.plot([], [], marker='o', color='#8e44ad', linewidth=2)
        self.ax.set_xlim(0, 1)
        self.ax.set_xticks([])

        # ==========================================
        # TARJETA 3: Parcela 1 (Humedad de Suelo)
        # ==========================================
        frame_suelo, info_suelo = self._crear_tarjeta(main_frame, 2, " Parcela: Parcela 1 (Humedad de Suelo) ", (8, 0))

        self._fila(info_suelo, 0, "Humedad promedio:", self.var_hum_suelo, "#8e44ad")

        ttk.Label(info_suelo, text="Estado:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.lbl_color_suelo = tk.Label(info_suelo, text="Esperando...", width=20, font=self.f_badge, fg="white", bg="gray")
        self.lbl_color_suelo.grid(row=1, column=1, sticky="w", padx=5, pady=2)

        ttk.Label(info_suelo, text="Qué hacer:").grid(row=2, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_accion_suelo = ttk.Label(info_suelo, text="...", wraplength=250)
        self.lbl_accion_suelo.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_accion_suelo, info_suelo, "col1"))

        self._fila(info_suelo, 3, "Tasa de secado:", self.var_tasa_secado)
        self._fila(info_suelo, 4, "Marchitez en:", self.var_tiempo_marchitez, "#c0392b")

        ttk.Label(info_suelo, text="Demanda cruzada:").grid(row=5, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_demanda = tk.Label(info_suelo, text="Esperando...", font=self.f_normal, fg="white", bg="gray",
                                    justify="left", anchor="w", wraplength=250, padx=6, pady=2)
        self.lbl_demanda.grid(row=5, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_demanda, info_suelo, "col1"))

        ttk.Label(info_suelo, text="Hoy:").grid(row=6, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_resumen_suelo = ttk.Label(info_suelo, textvariable=self.var_resumen_suelo, wraplength=250)
        self.lbl_resumen_suelo.grid(row=6, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_resumen_suelo, info_suelo, "col1"))

        self.fig_suelo, self.ax_suelo, self.canvas_suelo = self._crear_grafica(
            frame_suelo, "Histórico de Humedad de Suelo (%)")
        self.ax_suelo.axhspan(0, 30, color="#c0392b", alpha=0.12)
        self.ax_suelo.axhspan(30, 50, color="#f1c40f", alpha=0.18)
        self.ax_suelo.axhspan(50, 80, color="#27ae60", alpha=0.12)
        self.ax_suelo.axhspan(80, 105, color="#2980b9", alpha=0.12)
        self.ax_suelo.set_ylim(0, 105)
        for y, texto, color in [(91, "Asfixia", "#2980b9"), (77, "Capacidad de campo", "#27ae60"),
                                (46, "Estrés leve", "#b7950b"), (6, "Marchitez", "#c0392b")]:
            self.ax_suelo.text(0.99, y, texto, transform=self.ax_suelo.get_yaxis_transform(),
                               ha="right", va="center", fontsize=7, color=color, alpha=0.9, zorder=1)
        self.linea_suelo, = self.ax_suelo.plot([], [], marker='o', color='#2c3e50', linewidth=2, zorder=3)
        self.ax_suelo.set_xlim(0, 1)
        self.ax_suelo.set_xticks([])

        self.root.bind("<Configure>", self._on_resize)
        self.root.after(250, self._reajustar)

        self.configurar_mqtt()
        self.root.after(100, self._procesar_cola)

    def _crear_grafica_tacometro(self, tarjeta, titulo):
        fig = Figure(figsize=(4, 2.5), dpi=100)
        fig.patch.set_facecolor('#f0f0f0')
        ax = fig.add_subplot(111, polar=True)
        ax.set_title(titulo, fontsize=9, pad=10)

        theta_blue = np.linspace(np.pi, np.pi * (1 - 0.5/3.0), 100)
        theta_green = np.linspace(np.pi * (1 - 0.5/3.0), np.pi * (1 - 1.2/3.0), 100)
        theta_orange = np.linspace(np.pi * (1 - 1.2/3.0), np.pi * (1 - 2.5/3.0), 100)
        theta_red = np.linspace(np.pi * (1 - 2.5/3.0), 0, 100)

        ax.fill_between(theta_blue, 0, 1, color="#2980b9", alpha=0.6)
        ax.fill_between(theta_green, 0, 1, color="#27ae60", alpha=0.6)
        ax.fill_between(theta_orange, 0, 1, color="#f39c12", alpha=0.6)
        ax.fill_between(theta_red, 0, 1, color="#c0392b", alpha=0.6)

        ax.set_thetamin(0)
        ax.set_thetamax(180)
        ax.set_ylim(0, 1.2)
        ax.set_yticks([])
        ax.set_xticks([np.pi, np.pi * (1 - 0.5/3.0), np.pi * (1 - 1.2/3.0), np.pi * (1 - 2.5/3.0), 0])
        ax.set_xticklabels(['0', '0.5', '1.2', '2.5', '3.0'])

        self.flecha_dpv, = ax.plot([], [], color='black', linewidth=3)
        self.punto_dpv = ax.scatter([], [], color='black', s=50, zorder=5)

        fig.subplots_adjust(left=0.05, right=0.95, top=0.85, bottom=0.1)
        canvas = FigureCanvasTkAgg(fig, master=tarjeta)
        widget = canvas.get_tk_widget()
        widget.configure(width=200, height=150)
        widget.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        self.graficas.append({"fig": fig, "ax": ax, "canvas": canvas})
        return fig, ax, canvas

    def _crear_tarjeta(self, parent, columna, texto, padx):
        tarjeta = ttk.LabelFrame(parent, text=texto, padding=(10, 10))
        tarjeta.grid(row=0, column=columna, sticky="nsew", padx=padx, pady=5)
        tarjeta.columnconfigure(0, weight=1)
        tarjeta.rowconfigure(0, weight=0)
        tarjeta.rowconfigure(1, weight=1)
        info = ttk.Frame(tarjeta)
        info.grid(row=0, column=0, sticky="new", pady=(0, 5))
        info.columnconfigure(1, weight=1)
        self.tarjetas.append(tarjeta)
        self.infos.append(info)
        return tarjeta, info

    def _fila(self, parent, fila, texto, variable, color=None, pady=(2, 2)):
        ttk.Label(parent, text=texto).grid(row=fila, column=0, sticky="w", padx=5, pady=pady)
        kwargs = {"foreground": color} if color else {}
        ttk.Label(parent, textvariable=variable, font=self.f_valor, **kwargs).grid(
            row=fila, column=1, sticky="w", padx=5, pady=pady)

    def _nota(self, parent, fila, texto):
        lbl = ttk.Label(parent, text=texto, font=self.f_nota, foreground="gray", wraplength=300, justify="left")
        lbl.grid(row=fila, column=0, columnspan=2, sticky="w", padx=5)
        self._wrap_items.append((lbl, parent, "span"))

    def _crear_grafica(self, tarjeta, titulo):
        fig = Figure(figsize=(4, 2.5), dpi=100)
        fig.patch.set_facecolor('#f0f0f0')
        ax = fig.add_subplot(111)
        ax.set_title(titulo, fontsize=9)
        ax.set_ylim(0, 105)
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        ax.tick_params(axis='y', labelsize=8)
        fig.subplots_adjust(**MARGENES_GRAFICA)
        canvas = FigureCanvasTkAgg(fig, master=tarjeta)
        widget = canvas.get_tk_widget()
        widget.configure(width=200, height=150)
        widget.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.graficas.append({"fig": fig, "ax": ax, "canvas": canvas})
        return fig, ax, canvas

    def _on_resize(self, event):
        if event.widget is not self.root: return
        if self._job_resize: self.root.after_cancel(self._job_resize)
        self._job_resize = self.root.after(120, self._reajustar)

    def _reajustar(self):
        self._job_resize = None
        ancho = max(self.root.winfo_width(), 1)
        alto = max(self.root.winfo_height(), 1)
        if (ancho, alto) == self._ultimo_tam: return
        self._ultimo_tam = (ancho, alto)
        self.escala = max(0.75, min(1.6, min(ancho / ANCHO_BASE, alto / ALTO_BASE)))
        for nombre, fuente in self.fuentes.items():
            nuevo = max(7, round(self.tamanos_base[nombre] * self.escala))
            if fuente.cget("size") != nuevo: fuente.configure(size=nuevo)
        self.root.update_idletasks()
        self._actualizar_wraps()
        self.root.update_idletasks()
        self._sincronizar_alturas()
        self._estilo_graficas()

    def _actualizar_wraps(self):
        for lbl, frame, modo in self._wrap_items:
            ancho_frame = frame.winfo_width()
            if ancho_frame <= 1: continue
            if modo == "span": wrap = ancho_frame - 20
            else:
                ancho_col0 = frame.grid_bbox(0, 0)[2]
                wrap = ancho_frame - ancho_col0 - 30
            wrap = max(100, wrap)
            if int(float(str(lbl.cget("wraplength")))) != wrap: lbl.configure(wraplength=wrap)

    def _sincronizar_alturas(self):
        self.root.update_idletasks()
        altura = max(info.winfo_reqheight() for info in self.infos) + 5
        if altura != self._altura_info:
            self._altura_info = altura
            for tarjeta in self.tarjetas: tarjeta.rowconfigure(0, minsize=altura)

    def _estilo_graficas(self):
        for g in self.graficas:
            g["ax"].title.set_fontsize(max(7, 9 * self.escala))
            g["ax"].tick_params(axis='both', labelsize=max(6, 8 * self.escala))
            g["canvas"].draw_idle()

    def configurar_mqtt(self):
        self.cliente_mqtt = mqtt.Client(client_id=ID_CLIENTE, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.cliente_mqtt.username_pw_set(username=MQTT_USER, password=MQTT_PASSWORD)
        self.cliente_mqtt.on_connect = self.on_connect
        self.cliente_mqtt.on_message = self.on_message
        self.cliente_mqtt.connect(host=urlServidor, port=puerto)
        self.cliente_mqtt.loop_start()

    def on_connect(self, cliente, userdata, flags, reason_code, properties=None):
        cliente.subscribe(TOPICO_BASE_EDGE, qos=1)
        cliente.publish("campo1/dashboard/request/historial", "solicitud", qos=1)

    def on_message(self, cliente, userdata, message):
        self.cola_mensajes.put((message.topic, message.payload.decode('utf-8')))

    def _procesar_cola(self):
        hubo_cambio_texto = False
        try:
            while True:
                topico, payload = self.cola_mensajes.get_nowait()
                hubo_cambio_texto |= self._manejar_mensaje(topico, payload)
        except queue.Empty: pass
        if hubo_cambio_texto: self._sincronizar_alturas()
        self.root.after(100, self._procesar_cola)

    def renderizar_grafica_historica(self, payload):
        try:
            datos_json = json.loads(payload)
            if not datos_json: 
                self.linea_grafica.set_data([], [])
                self.ax.set_xticks([])
                self.ax.set_xticklabels([])
                self.canvas.draw_idle()
                return
                
            x_data = list(datos_json.keys())
            y_data = list(datos_json.values())
            self.linea_grafica.set_data(range(len(x_data)), y_data)
            
            posiciones_texto = []
            etiquetas_texto = []
            for i, hora in enumerate(x_data):
                if hora.endswith(":00"):
                    posiciones_texto.append(i)
                    etiquetas_texto.append(hora)
            
            self.ax.set_xticks(posiciones_texto)
            self.ax.set_xticklabels(etiquetas_texto, rotation=45, ha="right", fontsize=8)
            self.ax.set_xlim(0, max(1, len(x_data) - 1))
            self.canvas.draw_idle()
        except Exception as e: 
            print("Error renderizando JSON de luminosidad:", e)

    def renderizar_grafica_suelo_historica(self, payload):
        try:
            datos = json.loads(payload)
            serie = datos.get("serie", {})
            resumen = datos.get("resumen", {})
            if serie:
                x_data = list(serie.keys())
                y_data = list(serie.values())
                n = len(x_data)
                self.linea_suelo.set_data(range(n), y_data)
                self.ax_suelo.set_xticks(range(n))
                self.ax_suelo.set_xticklabels(x_data, rotation=45, ha="right")
                self.ax_suelo.set_xlim(max(0, n - PUNTOS_VISIBLES_SUELO) - 0.2, max(1, n - 1) + 0.2)
                self.canvas_suelo.draw_idle()
            if resumen:
                r = resumen['riegos']
                self.var_resumen_suelo.set(
                    f"Promedio {resumen['promedio']}% · {resumen['pct_optimo']}% en rango óptimo · "
                    f"{r} {'riego' if r == 1 else 'riegos'}")
        except Exception as e: print("Error renderizando histórico:", e)

    def actualizar_tacometro_dpv(self, val):
        val_clamped = min(max(val, 0), 3.0)
        angulo = np.pi * (1 - val_clamped / 3.0)
        self.flecha_dpv.set_data([angulo, angulo], [0, 0.9])
        self.punto_dpv.set_offsets([[angulo, 0]])
        self.canvas_dpv.draw_idle()
        if val <= 0.5: msg = "Ambiente muy húmedo. Riesgo de condensación."
        elif val <= 1.2: msg = "Rango óptimo para muchas plantas. Transpiración ideal."
        elif val <= 2.5: msg = "Ambiente más seco. Vigilar estrés hídrico."
        else: msg = "Condiciones muy secas y potencialmente peligrosas para la mayoría de las plantas."
        self.lbl_dpv_msg.config(text=msg)

    def actualizar_dpd(self, val):
        if val <= 2.0:
            color, texto = "#2980b9", "CONDENSACIÓN"
            pat = "Rocío inminente. Alto riesgo de germinación."
            agro = "Indeseable. El agua libre sobre la hoja lavará el producto químico."
        elif val <= 4.0:
            color, texto = "#f1c40f", "PRECAUCIÓN"
            pat = "Precaución. El margen térmico es estrecho."
            agro = "Riesgo de escurrimiento si la temperatura continúa bajando."
        elif val <= 8.0:
            color, texto = "#27ae60", "ÓPTIMO"
            pat = "Entorno seguro."
            agro = "Condiciones ideales."
        else:
            color, texto = "#c0392b", "SECO"
            pat = "Riesgo nulo."
            agro = "No recomendable. El producto se evaporará en el aire antes de que la hoja logre absorberlo."
        self.lbl_color_dpd.config(text=texto, bg=color)
        self.lbl_dpd_pat.config(text=pat)
        self.lbl_dpd_agro.config(text=agro)

    def actualizar_gdd(self, val):
        fases = [
            (65, "Pre-emergencia", "La semilla se encuentra en el suelo."),
            (150, "VE | Emergencia", "La semilla germina y el primer coleóptilo rompe la superficie del suelo."),
            (235, "V3 | Tercera hoja", "El punto de crecimiento sigue bajo tierra. La planta resiste heladas ligeras."),
            (340, "V6 | Sexta hoja", "El punto de crecimiento sale a la superficie. Se define genéticamente el número máximo de hileras."),
            (450, "V9 | Novena hoja", "Rápido crecimiento del tallo. Comienza una alta demanda de nitrógeno."),
            (650, "V12 | Doceava hoja", "Se define el tamaño y número de granos por hilera. La demanda de agua se dispara drásticamente."),
            (750, "VT | Espigamiento", "La última rama de la espiga es completamente visible. Máxima vulnerabilidad al déficit hídrico."),
            (850, "R1 | Floración / Sedas", "Emergen los estigmas. Etapa de mayor estrés térmico; riesgo de aborto de granos."),
            (1000, "R2 | Ampolla", "Los granos parecen pequeñas ampollas blancas llenas de un líquido transparente."),
            (1150, "R3 | Lechoso", "El interior del grano se vuelve blanco y lechoso debido a la acumulación de almidón."),
            (1300, "R4 | Masoso", "El líquido interno se espesa y adquiere una consistencia de masa."),
            (1600, "R5 | Dentado", "El grano comienza a secarse en la parte superior, formando una hendidura."),
            (float('inf'), "R6 | Madurez Fisiológica", "Se forma capa negra. El maíz está listo para la cosecha.")
        ]
        etapa = "Desconocida"
        hito = "Sin información"
        for limite, nom, desc in fases:
            if val < limite:
                etapa = nom
                hito = desc
                break
        self.lbl_gdd_etapa.config(text=etapa)
        self.lbl_gdd_hito.config(text=hito)

    def _manejar_mensaje(self, topico, payload):
        colores_hex = {"Gris": "#7f8c8d", "Azul": "#2980b9", "Verde": "#27ae60", "Amarillo": "#f1c40f", "Rojo": "#c0392b"}
        cambio_texto = False

        if "campo1/edge/parcelas/maiz1/temperatura/promedio" in topico: self.var_temp.set(f"{payload} °C")
        elif "campo1/edge/parcelas/maiz1/humedad_aire/promedio" in topico: self.var_hum_aire.set(f"{payload} %")
        elif "campo1/edge/parcelas/maiz1/dpv" in topico:
            try:
                val = float(payload)
                self.var_dpv.set(f"{val} kPa")
                self.actualizar_tacometro_dpv(val)
                cambio_texto = True
            except ValueError: pass
        elif "campo1/edge/parcelas/maiz1/dpd" in topico:
            try:
                val = float(payload)
                self.var_dpd.set(f"{val} °C")
                self.actualizar_dpd(val)
                cambio_texto = True
            except ValueError: pass
        elif "campo1/edge/parcelas/maiz1/gdd" in topico:
            try:
                val = float(payload)
                self.var_gdd.set(f"{val} Días Grado")
                self.actualizar_gdd(val)
                cambio_texto = True
            except ValueError: pass
        elif "campo1/edge/parcelas/parcela1/humedad_suelo/promedio" in topico:
            self.var_hum_suelo.set(f"{payload} %")
        elif "campo1/edge/parcelas/parcela1/humedad_suelo/tasa_secado" in topico:
            try:
                tasa = float(payload)
                self.var_tasa_secado.set("Humedeciendo" if tasa < 0 else f"{tasa} % / hora")
            except ValueError:
                self.var_tasa_secado.set(payload)
        elif "campo1/edge/parcelas/parcela1/humedad_suelo/tiempo_marchitez" in topico:
            self.var_tiempo_marchitez.set(payload)
            cambio_texto = True
        elif "campo1/edge/parcelas/parcela1/humedad_suelo/estado" in topico:
            datos = payload.split('|')
            if len(datos) == 3:
                zonas_suelo = {"Azul": "ASFIXIA", "Verde": "CAPACIDAD DE CAMPO",
                               "Amarillo": "ESTRÉS LEVE", "Rojo": "PUNTO DE MARCHITEZ"}
                self.lbl_color_suelo.config(text=zonas_suelo.get(datos[0], datos[0].upper()),
                                            bg=colores_hex.get(datos[0], "gray"))
                self.lbl_accion_suelo.config(text=f"{datos[1]} {datos[2]}")
                cambio_texto = True
        elif "campo1/edge/parcelas/parcela1/humedad_suelo/demanda_cruzada" in topico:
            datos = payload.split('|', 1)
            if len(datos) == 2:
                self.lbl_demanda.config(text=datos[1], bg=colores_hex.get(datos[0], "gray"),
                                        fg="#2c3e50" if datos[0] == "Amarillo" else "white")
                cambio_texto = True
        elif "campo1/edge/parcelas/parcela1/humedad_suelo/historial" in topico:
            self.renderizar_grafica_suelo_historica(payload)
            cambio_texto = True
        elif "campo1/edge/invernaderos/invernadero1/luminosidad/promedio" in topico:
            self.var_luminosidad.set(f"{payload} %")
        elif "campo1/edge/invernaderos/invernadero1/luminosidad/estado" in topico:
            datos = payload.split('|')
            if len(datos) == 3:
                self.lbl_color_lum.config(text=datos[0].upper(), bg=colores_hex.get(datos[0], "gray"))
                self.lbl_fisio_lum.config(text=datos[1])
                self.lbl_accion_lum.config(text=datos[2])
                cambio_texto = True
        elif "campo1/edge/invernaderos/invernadero1/luminosidad/historial" in topico:
            self.renderizar_grafica_historica(payload)

        return cambio_texto

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