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

// Estado en vivo cacheado para enriquecer el contexto de las alertas
const estadoLive = {
  luminosidadPct: null,
  sueloHumedadPct: null,
  sueloTasa: null,
  sueloEtaTexto: null,
  climaTemp: null,
  climaHumAire: null,
  climaDpv: null,
  climaDpd: null,
  gddAcumulado: null,
  gddEtapa: null,
};

// ==========================================================
// CLIENTE DE ALERTAS POR CORREO ELECTRÓNICO (EMAIL API)
// ==========================================================
const SEVERIDAD_CLIENTE = { Gris: 1, Verde: 0, Azul: 2, Amarillo: 2, Rojo: 3 };
const controlEnvioCliente = {}; // Evita ráfagas HTTP idénticas cada 2s por (kpi:subtipo)
const DEBOUNCE_HTTP_MS = 30 * 1000;

function mostrarToast(mensaje, nivel = "Verde") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  const claseNivel = `toast-${String(nivel).toLowerCase()}`;
  toast.className = `toast-item ${claseNivel}`;
  toast.textContent = mensaje;
  container.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, 6000);
}

function actualizarBadgeCorreo(kpi, estado, texto) {
  const badge = document.getElementById(`email-badge-${kpi}`);
  if (!badge) return;

  badge.classList.remove("hidden", "pill-cooldown", "pill-unconfigured");
  if (estado === "cooldown") {
    badge.classList.add("pill-cooldown");
  } else if (estado === "unconfigured") {
    badge.classList.add("pill-unconfigured");
  }
  badge.textContent = texto;
}

async function dispararAlertaEmail({
  kpi,
  subtipo = "general",
  zona,
  nivel,
  valor,
  diagnostico,
  accion,
}) {
  const ahora = Date.now();
  const sevActual = SEVERIDAD_CLIENTE[nivel] ?? 2;
  const clave = `${kpi}:${subtipo}`;
  const ultimo = controlEnvioCliente[clave];

  // Si ya enviamos este mismo (kpi + subtipo) en el mismo nivel hace menos de 30s, evitamos saturar fetch
  if (
    ultimo &&
    ahora - ultimo.ts < DEBOUNCE_HTTP_MS &&
    ultimo.nivel === nivel &&
    sevActual <= ultimo.severidad
  ) {
    return;
  }

  controlEnvioCliente[clave] = { ts: ahora, severidad: sevActual, nivel };

  const payload = {
    kpi,
    subtipo,
    zona,
    nivel,
    valor,
    diagnostico,
    accion,
    timestamp: new Date().toLocaleString("es-MX"),
  };

  try {
    const resp = await fetch("/api/alertas/email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await resp.json();
    const horaCorta = new Date().toLocaleTimeString();

    if (data.sent) {
      actualizarBadgeCorreo(kpi, "sent", `Alerta enviada (${horaCorta})`);
      mostrarToast(
        `Correo enviado [${kpi.toUpperCase()} · ${nivel}]: ${valor} -> ${data.recipients || ""}`,
        nivel
      );
    } else if (data.throttled) {
      actualizarBadgeCorreo(kpi, "cooldown", `Alerta enviada (en enfriamiento)`);
    } else if (data.code === "SMTP_NOT_CONFIGURED") {
      actualizarBadgeCorreo(kpi, "unconfigured", `⚠️ Riesgo detectado (configura .env)`);
      if (!ultimo?.avisoConfigMostrado) {
        mostrarToast(`⚠️ Alerta detectada en ${zona}, pero faltan credenciales SMTP en .env`, "Amarillo");
        controlEnvioCliente[clave].avisoConfigMostrado = true;
      }
    }
  } catch (err) {
    console.error("Error comunicando con /api/alertas/email:", err);
  }
}

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
    const kpiColor = chart.$kpiColor ?? "#0f172a";

    ctx.save();
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    const mainFontSize = Math.max(20, Math.round(innerRadius * 0.42));
    ctx.font = `800 ${mainFontSize}px "Segoe UI", system-ui, sans-serif`;
    ctx.fillStyle = kpiColor;
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
  kpiDoughnutChart.$kpiColor = "#0f172a";
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
        data: [0, 1600],
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
        borderColor: "#16a34a",
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
        y: { min: 0, title: { display: true, text: "GDD" } },
        x: { ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 12 } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

// ==========================================================
// KPI 1: MÓDULO INVERNADERO 1 (ILUMINACIÓN - LDR)
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
  estadoLive.luminosidadPct = clamped;
  const colorKey = clasificarLuminosidadJS(clamped);

  document.getElementById("lum-live-value").textContent = `${clamped.toFixed(2)} %`;
  const bar = document.getElementById("lum-progress-bar");
  bar.style.width = `${clamped}%`;
  bar.style.backgroundColor = COLORES[colorKey];
}

function actualizarEstadoLuminosidad(payload) {
  const partes = payload.split("|");
  if (partes.length < 3) return;

  const [colorRaw, fisiologia, accion] = partes;
  const color = colorRaw.trim();
  const badge = document.getElementById("lum-badge");
  badge.textContent = color.toUpperCase();
  badge.className = `state-badge state-${color.toLowerCase()}`;

  const lumFisio = document.getElementById("lum-fisio");
  lumFisio.textContent = fisiologia;
  if (color === "Rojo") {
    lumFisio.classList.add("texto-peligro");
  } else {
    lumFisio.classList.remove("texto-peligro");
  }
  document.getElementById("lum-accion").textContent = accion;

  const valPct =
    estadoLive.luminosidadPct !== null ? `${estadoLive.luminosidadPct.toFixed(2)} %` : "-- %";

  // Regla 1A: Radiación extrema (> 85%, Estado Rojo)
  if (color === "Rojo") {
    dispararAlertaEmail({
      kpi: "iluminacion",
      subtipo: "estres_luminico",
      zona: "Invernadero 1",
      nivel: "Rojo",
      valor: `Luminosidad: ${valPct} (Radiación Extrema > 85%)`,
      diagnostico: `${fisiologia} Riesgo agudo de fotoinhibición y estrés térmico foliar.`,
      accion,
    });
  }
  // Regla 1B: Luz baja (21% - 50%, Estado Azul)
  else if (color === "Azul") {
    dispararAlertaEmail({
      kpi: "iluminacion",
      subtipo: "estres_luminico",
      zona: "Invernadero 1",
      nivel: "Azul",
      valor: `Luminosidad: ${valPct} (Luz Baja 21–50%)`,
      diagnostico: `${fisiologia} Radiación fotosintéticamente activa insuficiente para el potencial del cultivo.`,
      accion,
    });
  }
  // Regla 1C: Fotosíntesis mínima o nula (<= 20%, Estado Gris)
  else if (color === "Gris") {
    dispararAlertaEmail({
      kpi: "iluminacion",
      subtipo: "estres_luminico",
      zona: "Invernadero 1",
      nivel: "Amarillo",
      valor: `Luminosidad: ${valPct} (Oscuridad / Fotosíntesis Nula <= 20%)`,
      diagnostico: `${fisiologia}`,
      accion,
    });
  }
}

function actualizarHistorialYKpi(payload) {
  try {
    const UMBRAL_EFICIENCIA = 70.0;
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

    const kpiContainer = document.querySelector("#modulo-iluminacion .kpi-section");

    if (diurnas > 0) {
      kpiDoughnutChart.$sinDatos = false;
      kpiDoughnutChart.$kpiTexto = `${eficiencia.toFixed(1)}%`;

      if (eficiencia < UMBRAL_EFICIENCIA) {
        kpiDoughnutChart.$kpiColor = COLORES.Rojo;
        kpiDoughnutChart.$kpiSubtexto = "⚠️ Baja Eficiencia";
        if (kpiContainer) kpiContainer.classList.add("alerta-kpi-container");

        // Regla 1D: Eficiencia Fotosintética Diaria < 70%
        const ventanasRiesgo = (conteo.Rojo || 0) + (conteo.Azul || 0);
        const nivelKpi = conteo.Rojo > 0 || eficiencia < 50 ? "Rojo" : "Amarillo";
        dispararAlertaEmail({
          kpi: "iluminacion",
          subtipo: "eficiencia_fotosintetica_diaria",
          zona: "Invernadero 1",
          nivel: nivelKpi,
          valor: `Eficiencia Diaria: ${eficiencia.toFixed(1)}% (< 70%) | Rojas: ${conteo.Rojo}, Azules: ${conteo.Azul}`,
          diagnostico: `El Índice de Eficiencia Fotosintética Diaria cayó a ${eficiencia.toFixed(1)}% con ${ventanasRiesgo} ventanas diurnas fuera del rango óptimo (51–85%).`,
          accion:
            conteo.Rojo >= conteo.Azul
              ? "Desplegar malla sombra al 30%-50% para mitigar exceso de radiación acumulada."
              : "Retirar mallas sombra y verificar posibles obstrucciones de luz en el invernadero.",
        });
      } else {
        kpiDoughnutChart.$kpiColor = "#0f172a";
        kpiDoughnutChart.$kpiSubtexto = "Eficiencia";
        if (kpiContainer) kpiContainer.classList.remove("alerta-kpi-container");
      }

      kpiDoughnutChart.data.labels = ["Azul (Luz baja)", "Verde (Óptimo)", "Rojo (Extrema)"];
      kpiDoughnutChart.data.datasets[0].data = [prop.Azul, prop.Verde, prop.Rojo];
      kpiDoughnutChart.data.datasets[0].backgroundColor = [COLORES.Azul, COLORES.Verde, COLORES.Rojo];
    } else {
      kpiDoughnutChart.$sinDatos = true;
      kpiDoughnutChart.$kpiTexto = "0.0%";
      kpiDoughnutChart.$kpiColor = "#0f172a";
      kpiDoughnutChart.$kpiSubtexto = "Sin luz útil";
      if (kpiContainer) kpiContainer.classList.remove("alerta-kpi-container");
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
// KPI 3: MÓDULO PARCELA 1 (HUMEDAD DE SUELO & TASA DE SECADO)
// ==========================================================
function clasificarSueloJS(valor) {
  if (valor >= 80) return "Azul";
  if (valor >= 50) return "Verde";
  if (valor >= 30) return "Amarillo";
  return "Rojo";
}

function parsearHorasMarchitez(textoEta) {
  if (!textoEta || typeof textoEta !== "string") return null;
  const limpio = textoEta.trim().toLowerCase();
  if (limpio.includes("ahora mismo")) return 0;
  const matchMin = limpio.match(/([\d.]+)\s*min/);
  if (matchMin) return Number.parseFloat(matchMin[1]) / 60.0;
  const matchHoras = limpio.match(/([\d.]+)\s*h/);
  if (matchHoras) return Number.parseFloat(matchHoras[1]);
  return null;
}

function actualizarSueloLive(payload) {
  const valor = Number.parseFloat(payload);
  if (Number.isNaN(valor)) return;

  const clamped = Math.max(0, Math.min(100, valor));
  estadoLive.sueloHumedadPct = clamped;
  const colorKey = clasificarSueloJS(clamped);

  document.getElementById("suelo-live-value").textContent = `${clamped.toFixed(1)} %`;
  const bar = document.getElementById("suelo-progress-bar");
  bar.style.width = `${clamped}%`;
  bar.style.backgroundColor = COLORES[colorKey];
}

function actualizarEstadoSuelo(payload) {
  const partes = payload.split("|");
  if (partes.length < 3) return;

  const [colorRaw, fisiologia, accion] = partes;
  const color = colorRaw.trim();
  const badge = document.getElementById("suelo-badge");
  badge.textContent = color.toUpperCase();
  badge.className = `state-badge state-${color.toLowerCase()}`;

  document.getElementById("suelo-fisio").textContent = fisiologia;
  document.getElementById("suelo-accion").textContent = accion;

  const humTxt =
    estadoLive.sueloHumedadPct !== null
      ? `${estadoLive.sueloHumedadPct.toFixed(1)} % VWC`
      : `Estado ${color}`;

  // Regla 3A: Suelo en Rojo (Marchitez < 30%), Azul (Saturación / Planta ahogándose >= 80%) o Amarillo (Estrés Leve 30-49%)
  if (color === "Rojo") {
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "estado_humedad_suelo",
      zona: "Parcela 1",
      nivel: "Rojo",
      valor: `Humedad Suelo: ${humTxt} (Punto de Marchitez < 30%)`,
      diagnostico: `${fisiologia} Déficit hídrico severo en zona radicular.`,
      accion,
    });
  } else if (color === "Azul") {
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "estado_humedad_suelo",
      zona: "Parcela 1",
      nivel: "Azul",
      valor: `Humedad Suelo: ${humTxt} (Saturación >= 80% — Riesgo de Ahogamiento)`,
      diagnostico: `${fisiologia} El exceso de agua desplaza el oxígeno del suelo; la planta se está ahogando (asfixia radicular y peligro de pudrición).`,
      accion,
    });
  } else if (color === "Amarillo") {
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "estado_humedad_suelo",
      zona: "Parcela 1",
      nivel: "Amarillo",
      valor: `Humedad Suelo: ${humTxt} (Estrés Hídrico Leve 30–49%)`,
      diagnostico: `${fisiologia}`,
      accion,
    });
  }
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

  estadoLive.sueloTasa = tasa;
  elValue.textContent = (tasa > 0 ? "+" : "") + tasa.toFixed(2);

  if (tasa > 1.5) {
    // Secado Rápido -> Semáforo ROJO
    elSub.textContent = "Secado acelerado (Riesgo hídrico)";
    elSub.style.color = "#dc2626";
    if (elBadge) {
      elBadge.textContent = "SECADO RÁPIDO";
      elBadge.className = "state-badge state-rojo";
    }

    // Regla 3B-1: Tasa de Secado muy alta (> 1.5 %/hora -> SECADO RÁPIDO)
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "tasa_secado",
      zona: "Parcela 1",
      nivel: "Rojo",
      valor: `Tasa de Secado: +${tasa.toFixed(2)} %/hora (SECADO RÁPIDO > 1.5 %/h)`,
      diagnostico:
        "La tasa de secado del suelo es críticamente alta (> 1.5 %/hora). Pérdida acelerada de humedad en la raíz.",
      accion:
        "Activar riego preventivo de inmediato y verificar la demanda evaporativa (DPV).",
    });
  } else if (tasa > 0.3) {
    // Secado Moderado -> Semáforo AMARILLO
    elSub.textContent = "Pérdida hídrica constante";
    elSub.style.color = "#dfaa18ff";
    if (elBadge) {
      elBadge.textContent = "SECADO NORMAL";
      elBadge.className = "state-badge state-amarillo";
    }

    // Regla 3B-2: Tasa de Secado moderada (0.3 a 1.5 %/hora)
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "tasa_secado",
      zona: "Parcela 1",
      nivel: "Amarillo",
      valor: `Tasa de Secado: +${tasa.toFixed(2)} %/hora (Pérdida Constante)`,
      diagnostico:
        "El suelo presenta una pérdida de humedad continua (> 0.3 %/hora). Monitorear evolución hacia el punto de marchitez.",
      accion: "Programar próximo turno de riego en Parcela 1.",
    });
  } else if (tasa >= -0.3 && tasa <= 0.3) {
    // Estable -> Semáforo VERDE
    elSub.textContent = "Humedad estable en raíz";
    elSub.style.color = "#166534";
    if (elBadge) {
      elBadge.textContent = "ESTABLE";
      elBadge.className = "state-badge state-verde";
    }
  } else {
    // Ganancia de Agua / Tasa Negativa (< -0.3 %/h) -> Semáforo AZUL
    elSub.textContent = "Absorción rápida / Exceso hídrico (Riesgo asfixia)";
    elSub.style.color = "#2563eb";
    if (elBadge) {
      elBadge.textContent = "EXCESO / RIEGO";
      elBadge.className = "state-badge state-azul";
    }

    // Regla 3B-3: Tasa de Secado muy baja / negativa (< -0.3 %/hora -> Exceso de agua / Planta ahogándose)
    const humActual =
      estadoLive.sueloHumedadPct !== null ? `${estadoLive.sueloHumedadPct.toFixed(1)}% VWC` : "--";
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "tasa_secado",
      zona: "Parcela 1",
      nivel: "Azul",
      valor: `Tasa de Secado: ${tasa.toFixed(2)} %/hora (Acumulación Hídrica | Humedad: ${humActual})`,
      diagnostico:
        "Tasa de secado negativa por ingreso acelerado de agua. Existe riesgo de saturación del suelo y asfixia radicular (la planta puede ahogarse por falta de oxígeno en la raíz).",
      accion:
        "Verificar si el riego sigue abierto, cerrar válvulas si se superó Capacidad de Campo y vigilar el drenaje.",
    });
  }
}

function actualizarTiempoMarchitez(payload) {
  estadoLive.sueloEtaTexto = payload;
  const elVal = document.getElementById("tiempo-marchitez-value");
  if (elVal) elVal.textContent = payload;
  const elChip = document.getElementById("suelo-marchitez-chip");
  if (elChip) elChip.textContent = `ETA: ${payload}`;

  // Regla 3C: Tiempo Estimado a Marchitez (ETA) <= 2h (Rojo) o <= 6h (Amarillo)
  const horasEta = parsearHorasMarchitez(payload);
  if (horasEta !== null && horasEta <= 2.0) {
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "tiempo_marchitez_eta",
      zona: "Parcela 1",
      nivel: "Rojo",
      valor: `ETA a Marchitez: ${payload} (Crítico <= 2 horas)`,
      diagnostico: `Al ritmo de secado actual, la humedad del suelo caerá al Punto de Marchitez (< 30%) en ${payload}.`,
      accion: "Iniciar riego de emergencia inmediatamente en Parcela 1.",
    });
  } else if (horasEta !== null && horasEta <= 6.0) {
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "tiempo_marchitez_eta",
      zona: "Parcela 1",
      nivel: "Amarillo",
      valor: `ETA a Marchitez: ${payload} (Preventivo <= 6 horas)`,
      diagnostico: `Tendencia de secado activa: el suelo alcanzará el Punto de Marchitez en ${payload}.`,
      accion: "Programar riego preventivo durante las próximas horas.",
    });
  }
}

function actualizarDemandaCruzada(payload) {
  const partes = payload.split("|");
  if (partes.length < 2) return;
  const [colorRaw, mensaje] = partes;
  const color = colorRaw.trim();

  const box = document.getElementById("demanda-cruzada-box");
  box.className = `cross-demand-box state-${color.toLowerCase()}-light`;
  document.getElementById("demanda-cruzada-texto").textContent = mensaje;

  // Regla 3D: Demanda Cruzada en Rojo o Amarillo
  if (color === "Rojo" || color === "Amarillo") {
    dispararAlertaEmail({
      kpi: "humedad_suelo",
      subtipo: "demanda_cruzada",
      zona: "Parcela 1",
      nivel: color,
      valor: `Demanda Cruzada ${color.toUpperCase()} (${estadoLive.sueloHumedadPct !== null ? estadoLive.sueloHumedadPct.toFixed(1) + "% VWC" : "--"})`,
      diagnostico: `Relación Atmósfera (DPV) vs Suelo: ${mensaje}`,
      accion:
        color === "Rojo"
          ? "Aplicar riego inmediato para contrarrestar la alta demanda evaporativa (DPV) y el secado radicular."
          : "Vigilar humedad radicular y programar riego ante demanda atmosférica elevada.",
    });
  }
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
// KPI 2: MÓDULO CLIMA MAÍZ 1 (GDD, DPV y DPD)
// ==========================================================
const ETAPAS_MAIZ_FALLBACK = [
  { gdd: 1600, nombre: "R6 - Madurez Fisiológica", descripcion: "Se forma capa negra en la base del grano. El maíz está listo para la cosecha." },
  { gdd: 1300, nombre: "R5 - Dentado (Dent)", descripcion: "El grano comienza a secarse en la parte superior, formando una hendidura." },
  { gdd: 1150, nombre: "R4 - Masoso (Dough)", descripcion: "El líquido interno se espesa y adquiere consistencia de masa." },
  { gdd: 1000, nombre: "R3 - Lechoso (Milk)", descripcion: "El interior del grano se vuelve blanco y lechoso por almidón." },
  { gdd: 850, nombre: "R2 - Ampolla (Blister)", descripcion: "Los granos parecen pequeñas ampollas blancas." },
  { gdd: 750, nombre: "R1 - Floración / Sedas (Silking)", descripcion: "Emergen los estigmas. Etapa de mayor estrés térmico; riesgo de aborto de granos." },
  { gdd: 650, nombre: "VT - Espigamiento (Tasseling)", descripcion: "Espiga visible. Máxima vulnerabilidad al déficit hídrico (DPV alto)." },
  { gdd: 450, nombre: "V12 - Doceava hoja", descripcion: "Se define el tamaño y número de granos por hilera. La demanda de agua se dispara drásticamente." },
  { gdd: 340, nombre: "V9 - Novena hoja", descripcion: "Rápido crecimiento del tallo. Alta demanda de nitrógeno." },
  { gdd: 235, nombre: "V6 - Sexta hoja", descripcion: "El punto de crecimiento sale a la superficie." },
  { gdd: 150, nombre: "V3 - Tercera hoja", descripcion: "El punto de crecimiento sigue bajo tierra." },
  { gdd: 65, nombre: "VE - Emergencia", descripcion: "La semilla germina y rompe la superficie del suelo." },
  { gdd: 0, nombre: "Pre-emergencia", descripcion: "La semilla se encuentra bajo tierra iniciando germinación." },
];

function obtenerEtapaFallback(gdd) {
  for (const e of ETAPAS_MAIZ_FALLBACK) {
    if (gdd >= e.gdd) return { nombre: e.nombre, descripcion: e.descripcion };
  }
  return { nombre: "Pre-emergencia", descripcion: "Iniciando acumulación térmica." };
}

function evaluarRiesgoFenologicoGdd(gdd, etapa) {
  const nombre = (etapa?.nombre || "").toUpperCase();
  const badgeGdd = document.getElementById("gdd-badge");

  // Regla 2A: Etapas fenológicas del maíz
  if (nombre.startsWith("VT") || nombre.includes("ESPIGAMIENTO")) {
    if (badgeGdd) {
      badgeGdd.textContent = "ETAPA CRÍTICA (VT)";
      badgeGdd.className = "state-badge state-rojo";
    }
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "etapa_fenologica_gdd",
      zona: "Parcela: Maíz 1",
      nivel: "Rojo",
      valor: `${gdd.toFixed(1)} GDD — ${etapa.nombre}`,
      diagnostico: `${etapa.descripcion} El cultivo se encuentra en su ventana de máxima sensibilidad al déficit hídrico.`,
      accion: "Garantizar humedad de suelo en Capacidad de Campo (50%–79%) y monitorear DPV continuamente.",
    });
  } else if (nombre.startsWith("R1") || nombre.includes("FLORACIÓN") || nombre.includes("SILKING")) {
    if (badgeGdd) {
      badgeGdd.textContent = "ETAPA CRÍTICA (R1)";
      badgeGdd.className = "state-badge state-rojo";
    }
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "etapa_fenologica_gdd",
      zona: "Parcela: Maíz 1",
      nivel: "Rojo",
      valor: `${gdd.toFixed(1)} GDD — ${etapa.nombre}`,
      diagnostico: `${etapa.descripcion} Riesgo crítico de aborto de granos ante golpes de calor o estrés evaporativo.`,
      accion: "Evitar cualquier déficit hídrico durante la polinización y aplicar riegos ligeros de refrescamiento si el DPV sube.",
    });
  } else if (nombre.startsWith("V12") || nombre.startsWith("V9") || nombre.startsWith("V6")) {
    if (badgeGdd) {
      badgeGdd.textContent = `ATENCIÓN (${nombre.split(" ")[0]})`;
      badgeGdd.className = "state-badge state-amarillo";
    }
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "etapa_fenologica_gdd",
      zona: "Parcela: Maíz 1",
      nivel: "Amarillo",
      valor: `${gdd.toFixed(1)} GDD — ${etapa.nombre}`,
      diagnostico: `${etapa.descripcion}`,
      accion: "Incrementar lámina de riego y verificar disponibilidad de nitrógeno para proteger el potencial de rendimiento.",
    });
  } else if (nombre.startsWith("R6") || nombre.includes("MADUREZ")) {
    if (badgeGdd) {
      badgeGdd.textContent = "COSECHA LISTA (R6)";
      badgeGdd.className = "state-badge state-azul";
    }
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "etapa_fenologica_gdd",
      zona: "Parcela: Maíz 1",
      nivel: "Azul",
      valor: `${gdd.toFixed(1)} GDD — ${etapa.nombre}`,
      diagnostico: `${etapa.descripcion}`,
      accion: "Suspender riegos programados y coordinar logística de cosecha por madurez fisiológica completada.",
    });
  } else if (badgeGdd) {
    badgeGdd.textContent = "ACTIVO";
    badgeGdd.className = "state-badge state-verde";
  }
}

function actualizarGddLive(payload) {
  try {
    const parsed = JSON.parse(payload);
    let gdd = 0;
    let etapa = null;

    if (typeof parsed === "number") {
      gdd = parsed;
      etapa = obtenerEtapaFallback(gdd);
    } else {
      gdd = Number(parsed.gdd_acumulado ?? 0);
      etapa = parsed.etapa_crecimiento || obtenerEtapaFallback(gdd);
    }

    estadoLive.gddAcumulado = gdd;
    estadoLive.gddEtapa = etapa.nombre;

    document.getElementById("gdd-etapa-nombre").textContent = etapa.nombre;
    document.getElementById("gdd-etapa-desc").textContent = etapa.descripcion;

    const faltante = Math.max(0, 1600 - gdd);
    window.gddCurrentVal = gdd;

    window.gddDoughnutChart.data.datasets[0].data = [gdd, faltante];

    if (!window.gddVistaFaltante) {
      window.gddDoughnutChart.$kpiTexto = gdd.toFixed(1);
    } else {
      window.gddDoughnutChart.$kpiTexto = faltante.toFixed(1);
    }

    window.gddDoughnutChart.update();

    evaluarRiesgoFenologicoGdd(gdd, etapa);
  } catch (err) {
    console.error("Error parseando payload de GDD:", err);
  }
}

function actualizarHistorialGdd(payload) {
  try {
    const serie = JSON.parse(payload);
    const fechas = serie.map((item) => item.fecha);
    const valores = serie.map((item) => item.gdd_acumulado);

    window.gddTrendChart.data.labels = fechas;
    window.gddTrendChart.data.datasets[0].data = valores;
    window.gddTrendChart.update();
  } catch (err) {
    console.error("Error parseando Historial de GDD:", err);
  }
}

function actualizarClimaTempHum() {
  const el = document.getElementById("clima-temp-hum-val");
  if (!el) return;
  const t = estadoLive.climaTemp !== null ? `${estadoLive.climaTemp.toFixed(1)} °C` : "-- °C";
  const h = estadoLive.climaHumAire !== null ? `${estadoLive.climaHumAire.toFixed(1)} %` : "-- %";
  el.textContent = `${t} / ${h}`;
}

function actualizarDpvClima(payload) {
  const dpv = Number.parseFloat(payload);
  if (Number.isNaN(dpv)) return;
  estadoLive.climaDpv = dpv;

  const elDpv = document.getElementById("clima-dpv-val");
  if (elDpv) {
    elDpv.textContent = `${dpv.toFixed(2)} kPa`;
    elDpv.style.color =
      dpv >= 2.5 ? COLORES.Rojo : dpv > 1.2 ? COLORES.Amarillo : dpv <= 0.5 ? COLORES.Azul : COLORES.Verde;
  }

  // Regla 2B: DPV Crítico (>= 2.5 kPa Rojo), Seco (> 1.2 kPa Amarillo) o Muy Húmedo (<= 0.5 kPa Azul)
  if (dpv >= 2.5) {
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "clima_dpv",
      zona: "Parcela: Maíz 1",
      nivel: "Rojo",
      valor: `DPV: ${dpv.toFixed(2)} kPa (Zona Roja >= 2.5 kPa)`,
      diagnostico:
        "Déficit de Presión de Vapor extremadamente alto. Atmósfera muy seca que provoca cierre estomático, detención fotosintética y estrés hídrico severo.",
      accion:
        "Activar riego de apoyo inmediatamente para compensar la demanda evaporativa atmosférica.",
    });
  } else if (dpv > 1.2) {
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "clima_dpv",
      zona: "Parcela: Maíz 1",
      nivel: "Amarillo",
      valor: `DPV: ${dpv.toFixed(2)} kPa (Ambiente Seco > 1.2 kPa)`,
      diagnostico:
        "Ambiente más seco del rango óptimo (0.5–1.2 kPa). Incremento en la tasa de transpiración del cultivo.",
      accion: "Vigilar humedad del suelo y preparar turno de riego preventivo.",
    });
  } else if (dpv <= 0.5) {
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "clima_dpv",
      zona: "Parcela: Maíz 1",
      nivel: "Azul",
      valor: `DPV: ${dpv.toFixed(2)} kPa (Ambiente Saturado <= 0.5 kPa)`,
      diagnostico:
        "Ambiente excesivamente húmedo. La planta no puede transpirar adecuadamente (transporte deficiente de nutrientes) y existe alto riesgo de condensación y hongos.",
      accion: "Evitar riegos adicionales y monitorear presencia de patógenos fúngicos.",
    });
  }
}

function actualizarDpdClima(payload) {
  const dpd = Number.parseFloat(payload);
  if (Number.isNaN(dpd)) return;
  estadoLive.climaDpd = dpd;

  const elDpd = document.getElementById("clima-dpd-val");
  if (elDpd) {
    elDpd.textContent = `${dpd.toFixed(2)} °C`;
    elDpd.style.color =
      dpd <= 2.0 ? COLORES.Azul : dpd <= 4.0 ? COLORES.Amarillo : dpd > 8.0 ? COLORES.Rojo : COLORES.Verde;
  }

  // Regla 2C: DPD Condensación (<= 2.0 °C Azul), Precaución (<= 4.0 °C Amarillo), Seco (> 8.0 °C Rojo)
  if (dpd <= 2.0) {
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "clima_dpd",
      zona: "Parcela: Maíz 1",
      nivel: "Azul",
      valor: `DPD: ${dpd.toFixed(2)} °C (Condensación <= 2.0 °C)`,
      diagnostico:
        "Depresión del Punto de Rocío crítica (<= 2 °C). Rocío inminente sobre la hoja; alto riesgo de germinación de hongos patógenos y lavado de agroquímicos.",
      accion:
        "Suspender aplicaciones de agroquímicos foliares y vigilar sanidad vegetal por patógenos.",
    });
  } else if (dpd <= 4.0) {
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "clima_dpd",
      zona: "Parcela: Maíz 1",
      nivel: "Amarillo",
      valor: `DPD: ${dpd.toFixed(2)} °C (Precaución 2.0–4.0 °C)`,
      diagnostico:
        "Margen térmico estrecho hacia el punto de rocío. Riesgo de escurrimiento foliar si la temperatura desciende.",
      accion: "Tomar precaución antes de programar aspersiones foliares.",
    });
  } else if (dpd > 8.0) {
    dispararAlertaEmail({
      kpi: "clima_gdd",
      subtipo: "clima_dpd",
      zona: "Parcela: Maíz 1",
      nivel: "Rojo",
      valor: `DPD: ${dpd.toFixed(2)} °C (Ambiente Seco > 8.0 °C)`,
      diagnostico:
        "Brecha térmica elevada respecto al punto de rocío. El producto agroquímico se evaporará en el aire antes de que la hoja logre absorberlo.",
      accion: "Posponer aplicación de agroquímicos foliares hasta que mejore la humedad relativa.",
    });
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
    prefix: "campo1/edge/parcelas/maiz1/",
    handle(topic, payload) {
      if (topic === "campo1/edge/parcelas/maiz1/gdd") actualizarGddLive(payload);
      else if (topic.endsWith("/historial_diario")) actualizarHistorialGdd(payload);
      else if (topic.endsWith("/dpv")) actualizarDpvClima(payload);
      else if (topic.endsWith("/dpd")) actualizarDpdClima(payload);
      else if (topic.endsWith("/temperatura/promedio")) {
        const val = Number.parseFloat(payload);
        if (!Number.isNaN(val)) {
          estadoLive.climaTemp = val;
          actualizarClimaTempHum();
        }
      } else if (topic.endsWith("/humedad_aire/promedio")) {
        const val = Number.parseFloat(payload);
        if (!Number.isNaN(val)) {
          estadoLive.climaHumAire = val;
          actualizarClimaTempHum();
        }
      }
    },
  },
];

// ==========================================================
// CONEXIÓN MQTT.JS SOBRE WEBSOCKETS (CON FALLBACK A GUEST)
// ==========================================================
function setStatus(text, cssClass) {
  const pill = document.getElementById("mqtt-status");
  pill.textContent = text;
  pill.className = `status-pill ${cssClass}`;
}

function conectarMQTT(usarGuestFallback = false) {
  const opciones = {
    ...MQTT_CONFIG.options,
    clientId: "web-dashboard-" + Math.random().toString(16).slice(2, 10),
  };

  if (usarGuestFallback) {
    opciones.username = "guest";
    opciones.password = "guest";
    console.warn("[MQTT] Probando conexión a RabbitMQ Web-MQTT con usuario por defecto (guest/guest)...");
  }

  const client = mqtt.connect(MQTT_CONFIG.url, opciones);
  let conectadoAlgunaVez = false;
  let intentosFallidos = 0;

  client.on("connect", () => {
    conectadoAlgunaVez = true;
    intentosFallidos = 0;
    setStatus(`Conectado (WS :15675 · ${opciones.username})`, "status-connected");
    client.subscribe(
      [MQTT_CONFIG.topics.iluminacion, MQTT_CONFIG.topics.suelo, MQTT_CONFIG.topics.maiz],
      { qos: 1 },
      (err) => {
        if (!err) {
          client.publish(MQTT_CONFIG.topics.requestHistorial, "solicitud", { qos: 1 });
        }
      }
    );
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

  client.on("reconnect", () => {
    intentosFallidos++;
    if (!conectadoAlgunaVez && !usarGuestFallback && intentosFallidos >= 2) {
      client.end(true);
      conectarMQTT(true);
      return;
    }
    setStatus(`Reconectando a WS :15675 (intento ${intentosFallidos})...`, "status-connecting");
  });

  client.on("offline", () => {
    if (conectadoAlgunaVez) {
      setStatus("Desconectado de RabbitMQ", "status-error");
    }
  });

  client.on("error", (err) => {
    console.error("Error MQTT WebSocket:", err);
    const msg = String(err?.message || err || "");
    if (
      !usarGuestFallback &&
      (msg.includes("Not authorized") || msg.includes("Bad username") || msg.includes("connack"))
    ) {
      client.end(true);
      conectarMQTT(true);
      return;
    }
    setStatus("Error de conexión WS (:15675)", "status-error");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  inicializarGraficas();
  conectarMQTT();
});
