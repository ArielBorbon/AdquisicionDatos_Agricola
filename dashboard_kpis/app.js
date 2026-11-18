import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import nodemailer from 'nodemailer';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Cargar variables de entorno desde dashboard_kpis/.env
dotenv.config({ path: path.join(__dirname, '.env') });

const app = express();
const port = Number(process.env.PORT) || 3000;
const publicDir = path.join(__dirname, 'public');

app.use(cors());
app.use(express.json());
app.use(express.static(publicDir));

app.get('/', (req, res) => {
  res.sendFile(path.join(publicDir, 'index.html'));
});

// ==========================================================
// CATÁLOGO DE LOS 3 KPIs PRINCIPALES Y JERARQUÍA DE RIESGO
// ==========================================================
const KPI_CATALOG = {
  iluminacion: {
    titulo: 'Índice de Eficiencia Fotosintética Diaria / Estrés Lumínico',
    sensor: 'Invernadero 1 - Sensor LDR',
    zonaDefault: 'Invernadero 1',
  },
  clima_gdd: {
    titulo: 'Grados Día de Desarrollo (GDD) / Clima (DPV y DPD)',
    sensor: 'Parcela Maíz 1 - Sensor DHT11',
    zonaDefault: 'Parcela: Maíz 1',
  },
  humedad_suelo: {
    titulo: 'Tasa de Secado, Tiempo a Marchitez y Demanda Cruzada',
    sensor: 'Parcela 1 - Sensor FC-28',
    zonaDefault: 'Parcela 1',
  },
};

const SEVERIDAD_NIVEL = {
  gris: 1,
  verde: 0,
  info: 1,
  azul: 2,
  amarillo: 2,
  rojo: 3,
  critico: 3,
  crítico: 3,
};

const COLORES_SEMAFORO = {
  rojo: {
    bg: '#dc2626',
    lightBg: '#fef2f2',
    border: '#f87171',
    text: '#991b1b',
    etiqueta: 'RIESGO CRÍTICO (ROJO)',
  },
  amarillo: {
    bg: '#eab308',
    lightBg: '#fefce8',
    border: '#facc15',
    text: '#854d0e',
    etiqueta: 'ALERTA PREVENTIVA (AMARILLO)',
  },
  azul: {
    bg: '#2563eb',
    lightBg: '#eff6ff',
    border: '#60a5fa',
    text: '#1e40af',
    etiqueta: 'ALERTA POR EXCESO / CONDICIÓN ESPECIAL (AZUL)',
  },
};

// Diccionario en memoria para Control Anti-Spam (Cooldown por KPI + subtipo)
// Estructura: { [clave]: { lastSentAt, kpi, subtipo, nivel, severidad, valor, totalEnvios } }
const registroAlertas = {};

function recargarEnv() {
  dotenv.config({ path: path.join(__dirname, '.env'), override: true });
}

function obtenerPassLimpia() {
  return (process.env.SMTP_PASS || '').replace(/\s+/g, '');
}

function obtenerCooldownMs() {
  recargarEnv();
  const minutos = Number(process.env.ALERT_COOLDOWN_MINUTES);
  return (Number.isFinite(minutos) && minutos > 0 ? minutos : 15) * 60 * 1000;
}

function normalizarNivel(nivel = 'Rojo') {
  const limpio = String(nivel).trim().toLowerCase();
  if (limpio.includes('amarillo')) return 'Amarillo';
  if (limpio.includes('azul')) return 'Azul';
  return 'Rojo';
}

function obtenerSeveridad(nivel) {
  const key = String(nivel || '').trim().toLowerCase();
  return SEVERIDAD_NIVEL[key] ?? 2;
}

function obtenerDestinatarios() {
  recargarEnv();
  const rawTo = (process.env.ALERT_EMAIL_TO || '').trim();
  const smtpUser = (process.env.SMTP_USER || '').trim();
  const lista = rawTo
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

    // Incluir también SMTP_USER como copia para garantizar recepción inmediata en la cuenta emisora
    if (smtpUser && !lista.includes(smtpUser)) {
      lista.push(smtpUser);
    }
    return lista.join(', ');
  }

  function smtpEstaConfigurado() {
    recargarEnv();
    const user = (process.env.SMTP_USER || '').trim();
    const pass = obtenerPassLimpia();
    const to = (process.env.ALERT_EMAIL_TO || '').trim();
    if (!user || !pass || !to) return false;
    if (
      user === 'tu_correo@gmail.com' ||
      pass === 'tu_contraseña_de_aplicacion' ||
      to === 'destinatario_alertas@gmail.com'
    ) {
      return false;
    }
    return true;
  }

  function crearTransporter() {
    recargarEnv();
    return nodemailer.createTransport({
      host: (process.env.SMTP_HOST || 'smtp.gmail.com').trim(),
      port: Number(process.env.SMTP_PORT) || 587,
      secure: String(process.env.SMTP_SECURE).toLowerCase() === 'true',
      auth: {
        user: (process.env.SMTP_USER || '').trim(),
        pass: obtenerPassLimpia(),
      },
    });
  }

  // ==========================================================
  // PLANTILLAS DE CORREO (TEXTO PLANO + HTML CON SEMÁFORO)
  // ==========================================================
  function construirTextoPlanoAlerta({
    kpi,
    kpiInfo,
    subtipo,
    zona,
    nivel,
    valor,
    diagnostico,
    accion,
    timestamp,
  }) {
    return [
      `ALERTA AGROIOT EDGE — NIVEL ${normalizarNivel(nivel).toUpperCase()}`,
      `==========================================================`,
      `KPI Afectado: ${kpiInfo.titulo} (${kpi}${subtipo ? ' / ' + subtipo : ''})`,
      `Zona / Sensor: ${zona} (${kpiInfo.sensor})`,
      `Nivel de Riesgo: ${normalizarNivel(nivel).toUpperCase()}`,
      `Valor Disparador: ${valor}`,
      `Fecha y Hora: ${timestamp}`,
      ``,
      `DIAGNÓSTICO FISIOLÓGICO:`,
      `${diagnostico}`,
      ``,
      `RECOMENDACIÓN DE ACCIÓN INMEDIATA:`,
      `${accion}`,
      `==========================================================`,
      `Sistema de Notificaciones AgroIoT (Node.js/Express + RabbitMQ)`,
    ].join('\n');
  }

  function construirHtmlAlerta({
    kpi,
    kpiInfo,
    subtipo,
    zona,
    nivel,
    valor,
    diagnostico,
    accion,
    timestamp,
    escaladoDesde,
    esPrueba = false,
  }) {
    const claveColor = normalizarNivel(nivel).toLowerCase();
    const tema = COLORES_SEMAFORO[claveColor] || COLORES_SEMAFORO.rojo;
    const cooldownMin = Number(process.env.ALERT_COOLDOWN_MINUTES) || 15;

    const badgeEscalado = escaladoDesde
      ? `<div style="margin-top:8px;display:inline-block;background:rgba(0,0,0,0.22);color:#ffffff;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700;">
         Cambio de estado: ${escaladoDesde.toUpperCase()} -> ${nivel.toUpperCase()}
       </div>`
      : '';

    const bannerPrueba = esPrueba
      ? `<div style="background:#eef2ff;border-left:4px solid #4f46e5;padding:10px 14px;margin-bottom:16px;border-radius:6px;color:#312e81;font-size:13px;">
         <strong>Correo de Prueba:</strong> Este mensaje fue disparado desde el Panel Agrícola IoT para verificar las alertas de los KPIs.
       </div>`
      : '';

    return `<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <title>Alerta AgroIoT - ${kpiInfo.titulo}</title>
</head>
<body style="margin:0;padding:24px;background-color:#f3f6f4;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#0f172a;">
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #dfe6e1;box-shadow:0 4px 18px rgba(15,23,42,0.08);">
    <tr>
      <td style="background-color:${tema.bg};padding:22px 26px;color:#ffffff;">
        <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;opacity:0.9;">
          AgroIoT Edge · Sistema Centralizado RabbitMQ
        </div>
        <h1 style="margin:6px 0 4px;font-size:20px;font-weight:800;">
          ${tema.etiqueta}
        </h1>
        <div style="font-size:14px;opacity:0.95;">
          ${kpiInfo.titulo}
        </div>
        ${badgeEscalado}
      </td>
    </tr>

    <tr>
      <td style="padding:24px 26px;">
        ${bannerPrueba}

        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:18px;">
          <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;width:38%;color:#64748b;font-size:13px;font-weight:600;">
              Módulo / KPI Afectado
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:14px;font-weight:700;color:#0f172a;">
              ${kpiInfo.titulo} <span style="font-weight:400;color:#64748b;">(${kpi}${subtipo ? ' · ' + subtipo : ''})</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;font-weight:600;">
              Zona Agrícola / Nodo
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:14px;font-weight:600;color:#0f172a;">
              ${zona} <span style="color:#64748b;font-weight:400;">— ${kpiInfo.sensor}</span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;font-weight:600;">
              Nivel de Semáforo
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;">
              <span style="display:inline-block;background:${tema.bg};color:#ffffff;padding:3px 10px;border-radius:6px;font-size:12px;font-weight:700;">
                ${normalizarNivel(nivel).toUpperCase()}
              </span>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;font-weight:600;">
              Valor Disparador
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:16px;font-weight:800;color:${tema.bg};">
              ${valor}
            </td>
          </tr>
          <tr>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;font-weight:600;">
              Fecha y Hora Exacta
            </td>
            <td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#334155;">
              ${timestamp}
            </td>
          </tr>
        </table>

        <div style="background:${tema.lightBg};border-left:4px solid ${tema.bg};padding:14px 16px;border-radius:8px;margin-bottom:14px;">
          <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:${tema.text};margin-bottom:4px;">
            Diagnóstico Fisiológico
          </div>
          <div style="font-size:14px;color:#1e293b;line-height:1.5;">
            ${diagnostico}
          </div>
        </div>

        <div style="background:#f8fafc;border:1px solid #cbd5e1;padding:14px 16px;border-radius:8px;">
          <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#0f172a;margin-bottom:4px;">
            Recomendación de Acción Inmediata
          </div>
          <div style="font-size:14px;font-weight:600;color:#0f172a;line-height:1.5;">
            ${accion}
          </div>
        </div>
      </td>
    </tr>

    <tr>
      <td style="background:#f8faf9;padding:14px 26px;border-top:1px solid #dfe6e1;font-size:12px;color:#64748b;text-align:center;">
        Notificación automática generada por <strong>AgroIoT Dashboard KPIs (Express + RabbitMQ Web-MQTT)</strong>.<br/>
        Control anti-spam activo: enfriamiento de <strong>${cooldownMin} min</strong> por indicador (salvo cambio de estado o escalamiento).
      </td>
    </tr>
  </table>
</body>
</html>`;
  }

  // ==========================================================
  // ENDPOINT PRINCIPAL: POST /api/alertas/email
  // ==========================================================
  app.post('/api/alertas/email', async (req, res) => {
    try {
      const {
        kpi,
        subtipo = 'general',
        zona,
        nivel = 'Rojo',
        valor = '--',
        diagnostico = 'Punto de riesgo detectado en telemetría del nodo Edge.',
        accion = 'Verificar condiciones en parcela/invernadero inmediatamente.',
        timestamp = new Date().toLocaleString('es-MX'),
      } = req.body || {};

      if (!kpi || !KPI_CATALOG[kpi]) {
        return res.status(400).json({
          ok: false,
          sent: false,
          message: `KPI inválido. Debe ser uno de: ${Object.keys(KPI_CATALOG).join(', ')}`,
        });
      }

      const kpiInfo = KPI_CATALOG[kpi];
      const nivelNormalizado = normalizarNivel(nivel);
      const severidadActual = obtenerSeveridad(nivelNormalizado);
      const ahora = Date.now();
      const cooldownMs = obtenerCooldownMs();

      // Clave por KPI + subtipo (permite que Tasa de Secado, Humedad, ETA, DPV, DPD, GDD e Iluminación
      // envíen sus respectivas alertas sin bloquearse mutuamente, y permite cambios ej. de Rojo a Azul)
      const claveCooldown = `${kpi}:${subtipo}`;
      const previo = registroAlertas[claveCooldown];
      let escaladoDesde = null;

      if (previo) {
        const transcurridoMs = ahora - previo.lastSentAt;
        const cambioEstado = previo.nivel !== nivelNormalizado;
        const escaloSeveridad = severidadActual > previo.severidad;

          // Bloquear únicamente si sigue en el mismo nivel/estado dentro de la ventana de cooldown
          if (transcurridoMs < cooldownMs && !cambioEstado && !escaloSeveridad) {
            const restanteSeg = Math.ceil((cooldownMs - transcurridoMs) / 1000);
            return res.status(200).json({
              ok: true,
              sent: false,
              throttled: true,
              kpi,
              subtipo,
              nivel: nivelNormalizado,
              remainingSeconds: restanteSeg,
              message: `Alerta (${subtipo}) en enfriamiento (${Math.ceil(restanteSeg / 60)} min restantes).`,
            });
          }

            if ((cambioEstado || escaloSeveridad) && transcurridoMs < cooldownMs) {
              escaladoDesde = previo.nivel;
            }
          }

          const zonaFinal = zona || kpiInfo.zonaDefault;
            const datosPlantilla = {
              kpi,
              kpiInfo,
              subtipo,
              zona: zonaFinal,
              nivel: nivelNormalizado,
              valor: String(valor),
              diagnostico: String(diagnostico),
              accion: String(accion),
              timestamp: String(timestamp),
              escaladoDesde,
              esPrueba: false,
        };

        const html = construirHtmlAlerta(datosPlantilla);
        const text = construirTextoPlanoAlerta(datosPlantilla);

        if (!smtpEstaConfigurado()) {
          console.warn(
              `[ALERTA-EMAIL][SIN CONFIGURAR .env] KPI=${kpi} (${subtipo}) | Nivel=${nivelNormalizado} | Valor=${valor}`
          );
          return res.status(503).json({
            ok: false,
            sent: false,
            code: 'SMTP_NOT_CONFIGURED',
            message:
              'Credenciales SMTP pendientes en dashboard_kpis/.env. Actualiza SMTP_USER, SMTP_PASS y ALERT_EMAIL_TO.',
          });
        }

        const transporter = crearTransporter();
        const destinatarios = obtenerDestinatarios();
        const asunto = `[AgroIoT - ${nivelNormalizado.toUpperCase()}] Alerta en ${zonaFinal}: ${kpiInfo.titulo}`;

        const info = await transporter.sendMail({
          from: `"AgroIoT Alertas KPI" <${(process.env.SMTP_USER || '').trim()}>`,
          to: destinatarios,
          subject: asunto,
          text,
          html,
        });

          registroAlertas[claveCooldown] = {
            lastSentAt: ahora,
            kpi,
            subtipo,
            nivel: nivelNormalizado,
            severidad: severidadActual,
            valor: String(valor),
            totalEnvios: (previo?.totalEnvios || 0) + 1,
          };

          console.log(
              `[ALERTA-EMAIL] Enviado (${info.messageId}) a [${destinatarios}] -> KPI=${kpi} (${subtipo}) | Nivel=${nivelNormalizado} | Valor=${valor}`
          );

          return res.status(200).json({
            ok: true,
            sent: true,
            throttled: false,
            kpi,
            subtipo,
            nivel: nivelNormalizado,
            recipients: destinatarios,
            escalatedFrom: escaladoDesde,
            messageId: info.messageId,
            message: `Alerta enviada a ${destinatarios}`,
          });
        } catch (error) {
          console.error('[ALERTA-EMAIL] Error enviando correo:', error);
          return res.status(500).json({
            ok: false,
            sent: false,
            message: `Error al enviar correo SMTP: ${error.message}`,
          });
        }
      });

  // ==========================================================
  // ENDPOINT DE PRUEBA: POST /api/alertas/test
  // Envía prueba de los 3 KPIs (o de uno específico)
  // ==========================================================
  app.post('/api/alertas/test', async (req, res) => {
    try {
      if (!smtpEstaConfigurado()) {
        return res.status(503).json({
          ok: false,
          sent: false,
          code: 'SMTP_NOT_CONFIGURED',
          message:
            'Configura primero tus credenciales reales (SMTP_USER, SMTP_PASS y ALERT_EMAIL_TO) en dashboard_kpis/.env',
        });
      }

      const transporter = crearTransporter();
      const destinatarios = obtenerDestinatarios();
      const ahoraStr = new Date().toLocaleString('es-MX');

      // Ejemplos representativos de los 3 KPIs para probar el sistema completo
      const pruebasKpis = [
        {
          kpi: 'iluminacion',
          subtipo: 'estres_luminico_y_eficiencia',
          zona: 'Invernadero 1',
          nivel: 'Rojo',
          valor: '92.4 % (Radiación Extrema > 85%) | Eficiencia Diaria: 58.3%',
          diagnostico:
            'Radiación solar extrema en Invernadero 1 con caída del Índice de Eficiencia Fotosintética Diaria (< 70%). Riesgo de fotoinhibición.',
          accion: 'Desplegar malla sombra al 30% o 50% inmediatamente.',
        },
        {
          kpi: 'clima_gdd',
          subtipo: 'etapa_critica_y_dpv_dpd',
          zona: 'Parcela: Maíz 1',
          nivel: 'Amarillo',
          valor: '685.0 GDD (VT - Espigamiento) | DPV: 2.65 kPa | DPD: 1.8 °C',
          diagnostico:
            'Cultivo en etapa crítica VT (Espigamiento) de máxima vulnerabilidad hídrica, con alta demanda evaporativa (DPV >= 2.5 kPa) y riesgo de rocío nocturno (DPD <= 2 °C).',
          accion:
            'Asegurar humedad en Capacidad de Campo para evitar aborto floral y suspender aspersiones foliares en horas de rocío.',
        },
        {
          kpi: 'humedad_suelo',
          subtipo: 'tasa_secado_y_asfixia',
          zona: 'Parcela 1',
          nivel: 'Azul',
          valor: 'Humedad: 84.5 % VWC | Tasa: -2.10 %/h (Exceso de Agua / Ahogamiento)',
          diagnostico:
            'Suelo saturado (>= 80%) y tasa de absorción excesiva. Las raíces carecen de oxígeno (planta ahogándose / riesgo de asfixia radicular y pudrición).',
          accion:
            'Suspender el riego inmediatamente en Parcela 1 y verificar el drenaje del terreno.',
        },
      ];

      // Si en el body piden solo 1 KPI específico, filtramos; si no, enviamos los 3 KPIs
      const kpiSolicitado = req.body?.kpi;
      const listaEnviar =
        kpiSolicitado && KPI_CATALOG[kpiSolicitado] && !req.body?.todos
          ? pruebasKpis.filter((p) => p.kpi === kpiSolicitado)
          : pruebasKpis;

      const resultados = [];
      for (const item of listaEnviar) {
        const kpiInfo = KPI_CATALOG[item.kpi];
        const datos = {
          ...item,
          kpiInfo,
          timestamp: ahoraStr,
          escaladoDesde: null,
          esPrueba: true,
        };
        const html = construirHtmlAlerta(datos);
        const text = construirTextoPlanoAlerta(datos);

        const info = await transporter.sendMail({
          from: `"AgroIoT Alertas KPI" <${(process.env.SMTP_USER || '').trim()}>`,
          to: destinatarios,
          subject: `[PRUEBA AgroIoT - ${item.nivel.toUpperCase()}] ${kpiInfo.titulo} (${item.zona})`,
          text,
          html,
        });

        resultados.push({ kpi: item.kpi, nivel: item.nivel, messageId: info.messageId });
        console.log(
          `[ALERTA-TEST] Correo enviado (${info.messageId}) -> KPI=${item.kpi} | Destinatarios=${destinatarios}`
        );
      }

      return res.status(200).json({
        ok: true,
        sent: true,
        recipients: destinatarios,
        resultados,
        message: `Se enviaron ${resultados.length} correos de prueba (3 KPIs) a: ${destinatarios}`,
      });
    } catch (error) {
      console.error('[ALERTA-TEST] Error en prueba SMTP:', error);
      const len = obtenerPassLimpia().length;
      const hint =
        len !== 16 && String(process.env.SMTP_HOST).includes('gmail')
          ? ` (Tu SMTP_PASS actual tiene ${len} letras; las Contraseñas de Aplicación de Google tienen exactamente 16 letras)`
          : '';
      return res.status(500).json({
        ok: false,
        sent: false,
        message: `Fallo en prueba SMTP: ${error.message}${hint}`,
      });
    }
  });

  app.get('/api/alertas/estado', (req, res) => {
    res.json({
      ok: true,
      smtpConfigured: smtpEstaConfigurado(),
      recipients: obtenerDestinatarios(),
      cooldownMinutes: Number(process.env.ALERT_COOLDOWN_MINUTES) || 15,
      registroAlertas,
    });
  });

  app.listen(port, () => {
    console.log(`Dashboard KPIs & Email API escuchando en http://localhost:${port}`);
  });
