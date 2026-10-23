import os
import sys
import json
import queue
from datetime import datetime

raiz_proyecto = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if raiz_proyecto not in sys.path:
    sys.path.append(raiz_proyecto)

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import paho.mqtt.client as mqtt
from edge.edge_meta_data import urlServidor, puerto

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque

ID_CLIENTE = "dashboard-agricola-principal"
MQTT_USER = "usuario_dashboard"
MQTT_PASSWORD = "password_seguro_dash"
TOPICO_BASE_EDGE = "campo1/#"

# Tamaño de ventana de referencia para calcular la escala de las fuentes
ANCHO_BASE = 1500
ALTO_BASE = 700

# Márgenes FIJOS (fracción de la figura) para que todas las gráficas tengan
# exactamente la misma caja de ejes y queden alineadas entre tarjetas.
MARGENES_GRAFICA = dict(left=0.11, right=0.97, top=0.88, bottom=0.22)


class DashboardAgricola:
    def __init__(self, root):
        self.root = root
        self.root.title("Dashboard de Monitoreo Agrícola IoT")
        self.root.geometry(f"{ANCHO_BASE}x{ALTO_BASE}")
        self.root.minsize(900, 520)
        self.root.configure(padx=20, pady=20)

        # Cola para pasar los mensajes MQTT (hilo de red) al hilo de Tk de forma segura
        self.cola_mensajes = queue.Queue()

        # ---------- Fuentes escalables (se ajustan al tamaño de la ventana) ----------
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

        # ---------- Variables ----------
        self.var_temp = tk.StringVar(value="Esperando datos...")
        self.var_hum_aire = tk.StringVar(value="Esperando datos...")
        self.var_dpv = tk.StringVar(value="Esperando datos...")
        self.var_dpd = tk.StringVar(value="Esperando datos...")
        self.var_gdd = tk.StringVar(value="Esperando datos...")
        self.var_hum_suelo = tk.StringVar(value="Esperando datos...")
        self.var_tasa_secado = tk.StringVar(value="Esperando datos...")
        self.var_luminosidad = tk.StringVar(value="Esperando datos...")

        # Estructuras para el comportamiento responsivo
        self.tarjetas = []      # LabelFrames (cada tarjeta)
        self.infos = []         # Frame superior de cada tarjeta (texto)
        self.graficas = []      # Figuras de matplotlib
        self._wrap_items = []   # Labels con texto largo que reajustan su wraplength
        self._job_resize = None
        self._ultimo_tam = None
        self._altura_info = None

        # ---------- Fila principal: 3 tarjetas del mismo ancho y alto ----------
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(0, weight=1)
        for col in range(3):
            main_frame.columnconfigure(col, weight=1, uniform="tarjetas")

        # ==========================================
        # TARJETA 1: Maíz (Clima) - sin gráfica por ahora
        # ==========================================
        frame_maiz, info_maiz = self._crear_tarjeta(main_frame, 0, " Parcela: Maíz 1 (Clima) ", (0, 8))

        self._fila(info_maiz, 0, "Temp Promedio:", self.var_temp, "#c0392b")
        self._fila(info_maiz, 1, "Hum Relativa Promedio:", self.var_hum_aire, "#2980b9")
        self._fila(info_maiz, 2, "DPV:", self.var_dpv)
        self._fila(info_maiz, 3, "DPD (Punto de Rocío):", self.var_dpd)
        self._fila(info_maiz, 4, "GDD Acumulado:", self.var_gdd)

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

        self.fig, self.ax, self.canvas = self._crear_grafica(
            frame_inv, "Tendencia Diaria de Luminosidad Promedio (Cada 30m)")
        self.linea_grafica, = self.ax.plot([], [], marker='o', color='#8e44ad', linewidth=2)
        self.ax.set_xlim(0, 1)
        self.ax.set_xticks([])

        # ==========================================
        # TARJETA 3: Parcela 1 (Humedad de Suelo)
        # ==========================================
        frame_suelo, info_suelo = self._crear_tarjeta(main_frame, 2, " Parcela: Parcela 1 (Humedad de Suelo) ", (8, 0))

        self._fila(info_suelo, 0, "Nivel de Humedad en Vivo:", self.var_hum_suelo, "#8e44ad")

        self._fila(info_suelo, 2, "Tasa de Secado:", self.var_tasa_secado, pady=(10, 2))
        self._nota(info_suelo, 3, "* Representa la pérdida de "
                                  "humedad en el suelo por cada hora, prediciendo cuándo será el próximo riego.")

        ttk.Label(info_suelo, text="Saturación:").grid(row=4, column=0, sticky="w", padx=5, pady=(10, 2))
        self.lbl_color_suelo = tk.Label(info_suelo, text="Esperando...", width=15, font=self.f_badge, fg="white", bg="gray")
        self.lbl_color_suelo.grid(row=4, column=1, sticky="w", padx=5, pady=(10, 2))
        self._nota(info_suelo, 5, "* Se evalua cada 1 minuto. Representa la capacidad "
                                  "del suelo para retener agua y el esfuerzo de la planta para absorberla.")

        ttk.Label(info_suelo, text="Diagnóstico:").grid(row=6, column=0, sticky="nw", padx=5, pady=(10, 2))
        self.lbl_diag_suelo = ttk.Label(info_suelo, text="...", wraplength=250)
        self.lbl_diag_suelo.grid(row=6, column=1, sticky="w", padx=5, pady=(10, 2))
        self._wrap_items.append((self.lbl_diag_suelo, info_suelo, "col1"))

        ttk.Label(info_suelo, text="Acción:").grid(row=7, column=0, sticky="nw", padx=5, pady=2)
        self.lbl_accion_suelo = ttk.Label(info_suelo, text="...", wraplength=250)
        self.lbl_accion_suelo.grid(row=7, column=1, sticky="w", padx=5, pady=2)
        self._wrap_items.append((self.lbl_accion_suelo, info_suelo, "col1"))

        self.fig_suelo, self.ax_suelo, self.canvas_suelo = self._crear_grafica(
            frame_suelo, "Monitoreo en Tiempo Real - Humedad de Suelo (%)")
        self.linea_suelo, = self.ax_suelo.plot([], [], marker='o', color='#2980b9', linewidth=2)

        # ---------- Buffer circular de suelo ----------
        self.historial_suelo_tiempo = deque(maxlen=15)
        self.historial_suelo_valores = deque(maxlen=15)

        # ---------- Responsividad ----------
        self.root.bind("<Configure>", self._on_resize)
        self.root.after(250, self._reajustar)

        # ---------- MQTT + procesamiento de cola en el hilo de Tk ----------
        self.configurar_mqtt()
        self.root.after(100, self._procesar_cola)

    # ==================================================
    # Constructores de UI reutilizables
    # ==================================================
    def _crear_tarjeta(self, parent, columna, texto, padx):
        """Tarjeta con 2 filas: fila 0 = información (altura sincronizada), fila 1 = gráfica (se expande)."""
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
        # Márgenes fijos: la caja de ejes es idéntica en todas las gráficas
        fig.subplots_adjust(**MARGENES_GRAFICA)

        canvas = FigureCanvasTkAgg(fig, master=tarjeta)
        widget = canvas.get_tk_widget()
        # Tamaño mínimo pequeño para que la gráfica pueda encogerse con la ventana
        widget.configure(width=200, height=150)
        widget.grid(row=1, column=0, sticky="nsew", pady=(10, 0))

        self.graficas.append({"fig": fig, "ax": ax, "canvas": canvas})
        return fig, ax, canvas

    # ==================================================
    # Responsividad (solo se ejecuta cuando cambia el tamaño de la ventana)
    # ==================================================
    def _on_resize(self, event):
        if event.widget is not self.root:
            return
        if self._job_resize:
            self.root.after_cancel(self._job_resize)
        self._job_resize = self.root.after(120, self._reajustar)

    def _reajustar(self):
        self._job_resize = None
        ancho = max(self.root.winfo_width(), 1)
        alto = max(self.root.winfo_height(), 1)

        # Si el tamaño no cambió, no hay nada que hacer (evita redibujados innecesarios)
        if (ancho, alto) == self._ultimo_tam:
            return
        self._ultimo_tam = (ancho, alto)

        # 1) Escalar fuentes (solo si el tamaño resultante cambió)
        self.escala = max(0.75, min(1.6, min(ancho / ANCHO_BASE, alto / ALTO_BASE)))
        for nombre, fuente in self.fuentes.items():
            nuevo = max(7, round(self.tamanos_base[nombre] * self.escala))
            if fuente.cget("size") != nuevo:
                fuente.configure(size=nuevo)
        self.root.update_idletasks()

        # 2) Salto de línea de los textos largos
        self._actualizar_wraps()
        self.root.update_idletasks()

        # 3) Igualar la altura de la zona de texto de las 3 tarjetas
        self._sincronizar_alturas()

        # 4) Tipografía de las gráficas
        self._estilo_graficas()

    def _actualizar_wraps(self):
        for lbl, frame, modo in self._wrap_items:
            ancho_frame = frame.winfo_width()
            if ancho_frame <= 1:
                continue
            if modo == "span":
                wrap = ancho_frame - 20
            else:
                ancho_col0 = frame.grid_bbox(0, 0)[2]
                wrap = ancho_frame - ancho_col0 - 30
            wrap = max(100, wrap)
            if int(float(str(lbl.cget("wraplength")))) != wrap:
                lbl.configure(wraplength=wrap)

    def _sincronizar_alturas(self):
        """
        Todas las tarjetas reservan la misma altura para su zona de texto (la de la más alta),
        así las gráficas empiezan en la misma línea. Solo se modifica si el valor cambia.
        """
        self.root.update_idletasks()
        altura = max(info.winfo_reqheight() for info in self.infos) + 5
        if altura != self._altura_info:
            self._altura_info = altura
            for tarjeta in self.tarjetas:
                tarjeta.rowconfigure(0, minsize=altura)

    def _estilo_graficas(self):
        for g in self.graficas:
            g["ax"].title.set_fontsize(max(7, 9 * self.escala))
            g["ax"].tick_params(axis='both', labelsize=max(6, 8 * self.escala))
            g["canvas"].draw_idle()

    # ==================================================
    # MQTT
    # ==================================================
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
        # Se ejecuta en el hilo de red de paho: NO se toca la UI aquí, solo se encola.
        self.cola_mensajes.put((message.topic, message.payload.decode('utf-8')))

    def _procesar_cola(self):
        """Se ejecuta en el hilo de Tk: vacía la cola y actualiza la UI de una sola vez."""
        hubo_cambio_texto = False
        grafica_suelo = False
        try:
            while True:
                topico, payload = self.cola_mensajes.get_nowait()
                cambio_texto, cambio_suelo = self._manejar_mensaje(topico, payload)
                hubo_cambio_texto |= cambio_texto
                grafica_suelo |= cambio_suelo
        except queue.Empty:
            pass

        # Un solo redibujado por lote de mensajes (en lugar de uno por mensaje)
        if grafica_suelo:
            self.renderizar_grafica_suelo_vivo()
        if hubo_cambio_texto:
            self._sincronizar_alturas()

        self.root.after(100, self._procesar_cola)

    # ==================================================
    # Gráficas
    # ==================================================
    def renderizar_grafica_historica(self, payload):
        try:
            datos_json = json.loads(payload)
            if not datos_json:
                return

            x_data = list(datos_json.keys())
            y_data = list(datos_json.values())

            self.linea_grafica.set_data(range(len(x_data)), y_data)
            self.ax.set_xticks(range(len(x_data)))
            self.ax.set_xticklabels(x_data, rotation=45, ha="right")
            self.ax.set_xlim(max(0, len(x_data) - 10), max(1, len(x_data) - 1))
            self.canvas.draw_idle()
        except Exception as e:
            print("Error renderizando JSON de Edge:", e)

    def renderizar_grafica_suelo_vivo(self):
        n = len(self.historial_suelo_tiempo)
        self.linea_suelo.set_data(range(n), list(self.historial_suelo_valores))
        self.ax_suelo.set_xticks(range(n))
        self.ax_suelo.set_xticklabels(list(self.historial_suelo_tiempo), rotation=45, ha="right")
        self.ax_suelo.set_xlim(-0.2, max(1, n - 1) + 0.2)
        self.canvas_suelo.draw_idle()

    # ==================================================
    # Manejo de mensajes (siempre en el hilo de Tk)
    # Devuelve (cambió_texto_que_afecta_alturas, hay_que_redibujar_suelo)
    # ==================================================
    def _manejar_mensaje(self, topico, payload):
        colores_hex = {"Gris": "#7f8c8d", "Azul": "#2980b9", "Verde": "#27ae60", "Amarillo": "#f1c40f", "Rojo": "#c0392b"}
        cambio_texto = False
        cambio_suelo = False

        # Modificación: Agregar "campo1/" a todas las cadenas de búsqueda
        if "campo1/edge/parcelas/maiz1/temperatura/promedio" in topico: self.var_temp.set(f"{payload} °C")
        elif "campo1/edge/parcelas/maiz1/humedad_aire/promedio" in topico: self.var_hum_aire.set(f"{payload} %")
        elif "campo1/edge/parcelas/maiz1/dpv" in topico: self.var_dpv.set(f"{payload} kPa")
        elif "campo1/edge/parcelas/maiz1/dpd" in topico: self.var_dpd.set(f"{payload} °C")
        elif "campo1/edge/parcelas/maiz1/gdd" in topico: self.var_gdd.set(f"{payload} Días Grado")

        elif "campo1/edge/parcelas/parcela1/humedad_suelo/tasa_secado" in topico: self.var_tasa_secado.set(f"{payload} % / hora")
        elif "campo1/edge/parcelas/parcela1/humedad_suelo/estado" in topico:
            datos = payload.split('|')
            if len(datos) == 3:
                self.lbl_color_suelo.config(text=datos[0].upper(), bg=colores_hex.get(datos[0], "gray"))
                self.lbl_diag_suelo.config(text=datos[1])
                self.lbl_accion_suelo.config(text=datos[2])
                cambio_texto = True

        elif "campo1/edge/invernaderos/invernadero1/luminosidad/promedio" in topico:
            self.var_luminosidad.set(f"{payload} %")
        elif "campo1/edge/invernaderos/invernadero1/luminosidad/estado" in topico:
            datos = payload.split('|')
            if len(datos) == 3:
                self.lbl_color_lum.config(text=datos[0].upper(), bg=colores_hex.get(datos[0], "gray"))
                self.lbl_fisio_lum.config(text=datos[1])
                cambio_texto = True

        elif "campo1/edge/invernaderos/invernadero1/luminosidad/historial" in topico:
            self.renderizar_grafica_historica(payload)

        # Esta regla ya estaba correcta (escucha directo al ESP32 sin pasar por el edge)
        elif "campo1/parcelas/parcela1/humedad/suelo" in topico and "edge" not in topico:
            try:
                str_fecha = payload[:19]
                str_valor = payload[19:].strip()
                dt_mensaje = datetime.strptime(str_fecha, "%d/%m/%Y %H:%M:%S")
                valor = float(str_valor)

                self.var_hum_suelo.set(f"{valor} %")

                self.historial_suelo_tiempo.append(dt_mensaje.strftime("%H:%M:%S"))
                self.historial_suelo_valores.append(valor)
                cambio_suelo = True
            except ValueError:
                pass

        return cambio_texto, cambio_suelo

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