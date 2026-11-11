// ==========================================================
// CONFIGURACIÓN RABBITMQ WEB-MQTT (Puerto 15675, ruta /ws)
// ==========================================================
const MQTT_CONFIG = {
  url: "ws://localhost:15675/ws",
  options: {
    clientId: "web-dashboard-" + Math.random().toString(16).slice(2, 10),
    protocolVersion: 4, // MQTT 3.1.1
    clean: true,
    reconnectPeriod: 3000,
    connectTimeout: 10000,
    username: "usuario_dashboard",
    password: "password_seguro_dash",
  },
  topics: {
    iluminacion: "campo1/edge/invernaderos/invernadero1/#",
    suelo: "campo1/edge/parcelas/parcela1/#",
    maiz: "campo1/edge/parcelas/maiz1/#",
    requestHistorial: "campo1/dashboard/request/historial",
  },
};

const COLORES = {
  Gris: "#64748b",
  Azul: "#2563eb",
  Verde: "#16a34a",
  Rojo: "#dc2626",
  Amarillo: "#eab308",
  Vacio: "#e2e8f0",
};

// ==========================================================
// PLUGIN CHART.JS v4: TEXTO CENTRAL EN GRÁFICA DE DONA
// ==========================================================
const kpiCenterTextPlugin = {
  id: "kpiCenterText",
  afterDraw(chart) {
    if (chart.config.type !== "doughnut") return;
    const meta = chart.getDatasetMeta(0);
    if (!meta || !meta.data.length) return;

    const { x, y, innerRadius } = meta.data[0];
    const { ctx } = chart;
    const kpiTexto = chart.$kpiTexto ?? "-- %";
    const kpiSubtexto = chart.$kpiSubtexto ?? "Eficiencia";

    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const mainFontSize = Math.max(20, Math.round(innerRadius * 0.42));
    ctx.font = `800 ${mainFontSize}px "Segoe UI", system-ui, sans-serif`;
    ctx.fillStyle = "#0f172a";
    ctx.fillText(kpiTexto, x, y - mainFontSize * 0.16);

    const subFontSize = Math.max(11, Math.round(innerRadius * 0.16));
    ctx.font = `600 ${subFontSize}px "Segoe UI", system-ui, sans-serif`;
    ctx.fillStyle = "#64748b";
    ctx.fillText(kpiSubtexto, x, y + mainFontSize * 0.48);

    ctx.restore();
  },
};

// ==========================================================
// INICIALIZACIÓN DE GRÁFICAS
// ==========================================================
let kpiDoughnutChart = null;
let lumTrendChart = null;
let sueloTrendChart = null;

function inicializarGraficas() {
  // 1. Dona de Iluminación
  const ctxDona = document.getElementById("kpi-doughnut-chart").getContext("2d");
  kpiDoughnutChart = new Chart(ctxDona, {
    type: "doughnut",
    data: {
      labels: ["Sin luz diurna"],
      datasets: [
        {
          data: [1],
          backgroundColor: [COLORES.Vacio],
          borderWidth: 2,
          borderColor: "#ffffff",
          hoverOffset: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { usePointStyle: true, padding: 14, font: { size: 12 } },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const label = context.label || "";
              const val = context.parsed;
              return context.chart.$sinDatos
                ? " Esperando ventanas con luz diurna"
                : ` ${label}: ${val}%`;
            },
          },
        },
      },
    },
    plugins: [kpiCenterTextPlugin],
  });
  kpiDoughnutChart.$kpiTexto = "-- %";
  kpiDoughnutChart.$kpiSubtexto = "Eficiencia";
  kpiDoughnutChart.$sinDatos = true;

  // 2. Tendencia de Iluminación (LDR)
  const ctxTrend = document.getElementById("lum-trend-chart").getContext("2d");
  lumTrendChart = new Chart(ctxTrend, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Luminosidad 30m (%)",
          data: [],
          borderColor: "#16a34a",
          backgroundColor: "rgba(22, 163, 74, 0.12)",
          borderWidth: 2,
          pointRadius: 3,
          fill: true,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } },
        x: { ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 8 } },
      },
      plugins: { legend: { display: false } },
    },
  });

  // 3. Tendencia de Curva de Secado (Humedad Suelo)
  const ctxSueloTrend = document.getElementById("suelo-trend-chart").getContext("2d");
  sueloTrendChart = new Chart(ctxSueloTrend, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Humedad Suelo (%)",
          data: [],
          borderColor: "#2563eb",
          backgroundColor: "rgba(37, 99, 235, 0.12)",
          borderWidth: 2,
          pointRadius: 3,
          fill: true,
          tension: 0.25,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } },
        x: { ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 8 } },
      },
      plugins: { legend: { display: false } },
    },
  });

  // 4. Dona de GDD (Maíz 1)
  const ctxGdd = document.getElementById("gdd-doughnut-chart").getContext("2d");
  window.gddDoughnutChart = new Chart(ctxGdd, {
    type: "doughnut",
    data: {
      labels: ["GDD Acumulado", "GDD Faltante"],
      datasets: [{
        data: [0, 1600], // 1600 es el umbral de R6 (Madurez)
        backgroundColor: [COLORES.Verde, COLORES.Vacio],
        borderWidth: 0,
        hoverOffset: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "75%",
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.parsed}` }
        },
      },
    },
    plugins: [kpiCenterTextPlugin],
  });
  window.gddDoughnutChart.$kpiTexto = "--";
  window.gddDoughnutChart.$kpiSubtexto = "GDD Acumulados";
  window.gddCurrentVal = 0;
  window.gddVistaFaltante = false;

  // Interactividad: Clic para voltear el valor (GDD Actual vs Faltante)
  document.getElementById("gdd-chart-container").addEventListener("click", () => {
    window.gddVistaFaltante = !window.gddVistaFaltante;
    if (window.gddVistaFaltante) {
      const faltante = Math.max(0, 1600 - window.gddCurrentVal);
      window.gddDoughnutChart.$kpiTexto = faltante.toFixed(1);
      window.gddDoughnutChart.$kpiSubtexto = "GDD Faltantes (R6)";
    } else {
      window.gddDoughnutChart.$kpiTexto = window.gddCurrentVal.toFixed(1);
      window.gddDoughnutChart.$kpiSubtexto = "GDD Acumulados";
    }
    window.gddDoughnutChart.update();
  });

  // 5. Tendencia Histórica GDD
  const ctxGddTrend = document.getElementById("gdd-trend-chart").getContext("2d");
  window.gddTrendChart = new Chart(ctxGddTrend, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "GDD Acumulado",
        data: [],
        borderColor: "#16a34a", // Verde estilo banano
        backgroundColor: "rgba(22, 163, 74, 0.0)",
        borderWidth: 3,
        pointRadius: 4,
        pointBackgroundColor: "#16a34a",
        fill: false,
        tension: 0.1,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: { min: 0, title: { display: true, text: 'GDD' } },
        x: { ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

// ==========================================================
// LÓGICA DEL MÓDULO: INVERNADERO 1 (ILUMINACIÓN)
// ==========================================================
function clasificarLuminosidadJS(valor) {
  if (valor <= 20) return "Gris";
  if (valor <= 50) return "Azul";
  if (valor <= 85) return "Verde";
  return "Rojo";
}

function calcularKpiFallback(serie) {
  const conteo = { Gris: 0, Azul: 0, Verde: 0, Rojo: 0 };
  for (const val of Object.values(serie)) {
    conteo[clasificarLuminosidadJS(Number(val))]++;
  }
  const diurnas = conteo.Azul + conteo.Verde + conteo.Rojo;
  const eficiencia = diurnas > 0 ? Number(((conteo.Verde / diurnas) * 100).toFixed(2)) : 0;
  return {
    eficiencia_fotosintetica: eficiencia,
    ventanas_diurnas: diurnas,
    conteo_estados: conteo,
    proporciones_diurnas_pct: {
      Azul: diurnas > 0 ? Number(((conteo.Azul / diurnas) * 100).toFixed(2)) : 0,
      Verde: diurnas > 0 ? Number(((conteo.Verde / diurnas) * 100).toFixed(2)) : 0,
      Rojo: diurnas > 0 ? Number(((conteo.Rojo / diurnas) * 100).toFixed(2)) : 0,
    },
  };
}

function actualizarLuminosidadLive(payload) {
  const valor = Number.parseFloat(payload);
  if (Number.isNaN(valor)) return;

  const clamped = Math.max(0, Math.min(100, valor));
  const colorKey = clasificarLuminosidadJS(clamped);

  document.getElementById("lum-live-value").textContent = `${clamped.toFixed(2)} %`;
  const bar = document.getElementById("lum-progress-bar");
  bar.style.width = `${clamped}%`;
  bar.style.backgroundColor = COLORES[colorKey];
}

function actualizarEstadoLuminosidad(payload) {
  const partes = payload.split("|");
  if (partes.length < 3) return;

  const [color, fisiologia, accion] = partes;
  const badge = document.getElementById("lum-badge");
  badge.textContent = color.toUpperCase();
  badge.className = `state-badge state-${color.toLowerCase()}`;

  document.getElementById("lum-fisio").textContent = fisiologia;
  document.getElementById("lum-accion").textContent = accion;
}

function actualizarHistorialYKpi(payload) {
  try {
    const data = JSON.parse(payload);
    const serie = data.serie && typeof data.serie === "object" ? data.serie : data;
    const kpi = data.kpi || calcularKpiFallback(serie);

    if (data.fecha) {
      document.getElementById("kpi-fecha").textContent = data.fecha;
    }
    const horas = Object.keys(serie);
    const valores = Object.values(serie);
    lumTrendChart.data.labels = horas;
    lumTrendChart.data.datasets[0].data = valores;
    lumTrendChart.update();

    const conteo = kpi.conteo_estados || { Gris: 0, Azul: 0, Verde: 0, Rojo: 0 };
    const prop = kpi.proporciones_diurnas_pct || { Azul: 0, Verde: 0, Rojo: 0 };
    const diurnas = kpi.ventanas_diurnas ?? (conteo.Azul + conteo.Verde + conteo.Rojo);
    const eficiencia = Number(kpi.eficiencia_fotosintetica ?? 0);

    document.getElementById("kpi-ventanas-diurnas").textContent =
      `${diurnas} ${diurnas === 1 ? "ventana diurna" : "ventanas diurnas"}`;
    document.getElementById("count-azul").textContent = `${conteo.Azul} (${prop.Azul}%)`;
    document.getElementById("count-verde").textContent = `${conteo.Verde} (${prop.Verde}%)`;
    document.getElementById("count-rojo").textContent = `${conteo.Rojo} (${prop.Rojo}%)`;
    document.getElementById("count-gris").textContent = `${conteo.Gris}`;

    if (diurnas > 0) {
      kpiDoughnutChart.$sinDatos = false;
      kpiDoughnutChart.$kpiTexto = `${eficiencia.toFixed(1)}%`;
      kpiDoughnutChart.$kpiSubtexto = "Eficiencia";
      kpiDoughnutChart.data.labels = ["Azul (Luz baja)", "Verde (Óptimo)", "Rojo (Extrema)"];
      kpiDoughnutChart.data.datasets[0].data = [prop.Azul, prop.Verde, prop.Rojo];
      kpiDoughnutChart.data.datasets[0].backgroundColor = [COLORES.Azul, COLORES.Verde, COLORES.Rojo];
    } else {
      kpiDoughnutChart.$sinDatos = true;
      kpiDoughnutChart.$kpiTexto = "0.0%";
      kpiDoughnutChart.$kpiSubtexto = "Sin luz útil";
      kpiDoughnutChart.data.labels = ["Sin luz diurna"];
      kpiDoughnutChart.data.datasets[0].data = [1];
      kpiDoughnutChart.data.datasets[0].backgroundColor = [COLORES.Vacio];
    }
    kpiDoughnutChart.update();
  } catch (err) {
    console.error("Error procesando historial/KPI de luminosidad:", err);
  }
}

// ==========================================================
// LÓGICA DEL MÓDULO: PARCELA 1 (HUMEDAD DE SUELO & TASA DE SECADO)
// ==========================================================
function clasificarSueloJS(valor) {
  if (valor >= 80) return "Azul";
  if (valor >= 50) return "Verde";
  if (valor >= 30) return "Amarillo";
  return "Rojo";
}

function actualizarSueloLive(payload) {
  const valor = Number.parseFloat(payload);
  if (Number.isNaN(valor)) return;

  const clamped = Math.max(0, Math.min(100, valor));
  const colorKey = clasificarSueloJS(clamped);

  document.getElementById("suelo-live-value").textContent = `${clamped.toFixed(1)} %`;
  const bar = document.getElementById("suelo-progress-bar");
  bar.style.width = `${clamped}%`;
  bar.style.backgroundColor = COLORES[colorKey];
}

function actualizarEstadoSuelo(payload) {
  const partes = payload.split("|");
  if (partes.length < 3) return;

  const [color, fisiologia, accion] = partes;
  const badge = document.getElementById("suelo-badge");
  badge.textContent = color.toUpperCase();
  badge.className = `state-badge state-${color.toLowerCase()}`;

  document.getElementById("suelo-fisio").textContent = fisiologia;
  document.getElementById("suelo-accion").textContent = accion;
}

function actualizarTasaSecado(payload) {
  const tasa = Number.parseFloat(payload);
  const elValue = document.getElementById("tasa-secado-value");
  const elSub = document.getElementById("tasa-secado-sub");
  const elBadge = document.getElementById("tasa-secado-badge");

  if (Number.isNaN(tasa)) {
    elValue.textContent = "--";
    elSub.textContent = "Calculando tendencia...";
    if (elBadge) {
      elBadge.textContent = "CALCULANDO";
      elBadge.className = "state-badge state-gris";
    }
    return;
  }

  elValue.textContent = (tasa > 0 ? "+" : "") + tasa.toFixed(2);

  if (tasa > 1.5) {
    // Secado Rápido -> Semáforo ROJO
    elSub.textContent = "Secado acelerado (Riesgo hídrico)";
    elSub.style.color = "#dc2626";
    if (elBadge) {
      elBadge.textContent = "SECADO RÁPIDO";
      elBadge.className = "state-badge state-rojo";
    }
  } else if (tasa > 0.3) {
    // Secado Moderado -> Semáforo AMARILLO
    elSub.textContent = "Pérdida hídrica constante";
    elSub.style.color = "#dfaa18ff";
    if (elBadge) {
      elBadge.textContent = "SECADO NORMAL";
      elBadge.className = "state-badge state-amarillo";
    }
  } else if (tasa >= -0.3 && tasa <= 0.3) {
    // Estable -> Semáforo VERDE
    elSub.textContent = "Humedad estable en raíz";
    elSub.style.color = "#166534";
    if (elBadge) {
      elBadge.textContent = "ESTABLE";
      elBadge.className = "state-badge state-verde";
    }
  } else {
    // Ganancia de Agua (Riego / Lluvia) -> Semáforo AZUL
    elSub.textContent = "Absorción de humedad (Riego/Lluvia)";
    elSub.style.color = "#2563eb";
    if (elBadge) {
      elBadge.textContent = "RECUPERACIÓN";
      elBadge.className = "state-badge state-azul";
    }
  }
}

function actualizarTiempoMarchitez(payload) {
  document.getElementById("tiempo-marchitez-value").textContent = payload;
  document.getElementById("suelo-marchitez-chip").textContent = `ETA: ${payload}`;
}

function actualizarDemandaCruzada(payload) {
  const partes = payload.split("|");
  if (partes.length < 2) return;
  const [color, mensaje] = partes;

  const box = document.getElementById("demanda-cruzada-box");
  box.className = `cross-demand-box state-${color.toLowerCase()}-light`;
  document.getElementById("demanda-cruzada-texto").textContent = mensaje;
}

function actualizarHistorialSuelo(payload) {
  try {
    const data = JSON.parse(payload);
    const serie = data.serie || {};
    const resumen = data.resumen || {};

    const horas = Object.keys(serie);
    const valores = Object.values(serie);

    if (sueloTrendChart) {
      sueloTrendChart.data.labels = horas;
      sueloTrendChart.data.datasets[0].data = valores;
      sueloTrendChart.update();
    }

    if (resumen.promedio !== undefined) {
      document.getElementById("suelo-hist-resumen").textContent = `${resumen.promedio}% prom (${resumen.riegos} riegos)`;
    }
  } catch (err) {
    console.error("Error procesando historial de suelo:", err);
  }
}

// ==========================================================
// LÓGICA DEL MÓDULO: CLIMA MAÍZ 1 (GDD)
// ==========================================================
function actualizarGddLive(payload) {
  try {
    const data = JSON.parse(payload);
    const gdd = data.gdd_acumulado;
    const etapa = data.etapa_crecimiento;

    // Actualizar Textos
    document.getElementById("gdd-etapa-nombre").textContent = etapa.nombre;
    document.getElementById("gdd-etapa-desc").textContent = etapa.descripcion;

    // Actualizar Gráfica Circular
    const faltante = Math.max(0, 1600 - gdd);
    window.gddCurrentVal = gdd;
    
    window.gddDoughnutChart.data.datasets[0].data = [gdd, faltante];
    
    // Si no está en vista invertida, actualizar el texto central
    if (!window.gddVistaFaltante) {
      window.gddDoughnutChart.$kpiTexto = gdd.toFixed(1);
    } else {
      window.gddDoughnutChart.$kpiTexto = faltante.toFixed(1);
    }
    
    window.gddDoughnutChart.update();
  } catch (err) {
    console.error("Error parseando JSON de GDD:", err);
  }
}

function actualizarHistorialGdd(payload) {
  try {
    const serie = JSON.parse(payload);
    // serie es un array: [{"fecha": "2026-10-01", "gdd_acumulado": 15}, ...]
    
    const fechas = serie.map(item => item.fecha);
    const valores = serie.map(item => item.gdd_acumulado);

    window.gddTrendChart.data.labels = fechas;
    window.gddTrendChart.data.datasets[0].data = valores;
    window.gddTrendChart.update();
  } catch (err) {
    console.error("Error parseando Historial de GDD:", err);
  }
}

// ==========================================================
// ENRUTADOR MODULAR DE TÓPICOS MQTT
// ==========================================================
const MODULE_HANDLERS = [
  {
    prefix: "campo1/edge/invernaderos/invernadero1/luminosidad/",
    handle(topic, payload) {
      if (topic.endsWith("/promedio")) actualizarLuminosidadLive(payload);
      else if (topic.endsWith("/estado")) actualizarEstadoLuminosidad(payload);
      else if (topic.endsWith("/historial")) actualizarHistorialYKpi(payload);
    },
  },
  {
    prefix: "campo1/edge/parcelas/parcela1/humedad_suelo/",
    handle(topic, payload) {
      if (topic.endsWith("/promedio")) actualizarSueloLive(payload);
      else if (topic.endsWith("/estado")) actualizarEstadoSuelo(payload);
      else if (topic.endsWith("/tasa_secado")) actualizarTasaSecado(payload);
      else if (topic.endsWith("/tiempo_marchitez")) actualizarTiempoMarchitez(payload);
      else if (topic.endsWith("/demanda_cruzada")) actualizarDemandaCruzada(payload);
      else if (topic.endsWith("/historial")) actualizarHistorialSuelo(payload);
    },
  },
  {
    prefix: "campo1/edge/parcelas/maiz1/gdd",
    handle(topic, payload) {
      if (topic === "campo1/edge/parcelas/maiz1/gdd") actualizarGddLive(payload);
      else if (topic.endsWith("/historial_diario")) actualizarHistorialGdd(payload);
    },
  }
];

// ==========================================================
// CONEXIÓN MQTT.JS SOBRE WEBSOCKETS
// ==========================================================
function setStatus(text, cssClass) {
  const pill = document.getElementById("mqtt-status");
  pill.textContent = text;
  pill.className = `status-pill ${cssClass}`;
}

function conectarMQTT() {
  const client = mqtt.connect(MQTT_CONFIG.url, MQTT_CONFIG.options);

  client.on("connect", () => {
    setStatus("Conectado (WS :15675)", "status-connected");
    // Suscripción a Iluminación y Suelo
    client.subscribe([MQTT_CONFIG.topics.iluminacion, MQTT_CONFIG.topics.suelo, MQTT_CONFIG.topics.maiz], { qos: 1 }, (err) => {
      if (!err) {
        client.publish(MQTT_CONFIG.topics.requestHistorial, "solicitud", { qos: 1 });
      }
    });
  });

  client.on("message", (topic, messageBuffer) => {
    const payload = messageBuffer.toString("utf-8");
    document.getElementById("last-update").textContent =
      `Último dato: ${new Date().toLocaleTimeString()}`;

    for (const handler of MODULE_HANDLERS) {
      if (topic.startsWith(handler.prefix)) {
        handler.handle(topic, payload);
      }
    }
  });

  client.on("reconnect", () => setStatus("Reconectando...", "status-connecting"));
  client.on("offline", () => setStatus("Desconectado", "status-error"));
  client.on("error", (err) => {
    console.error("Error MQTT WebSocket:", err);
    setStatus("Error de conexión WS", "status-error");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  inicializarGraficas();
  conectarMQTT();
});