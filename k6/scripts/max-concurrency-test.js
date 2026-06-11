/**
 * K6 Max Model Concurrency Experiment — vLLM (Qwen2.5-7B)
 *
 * Objetivo: encontrar el punto de saturación de --max-num-seqs y medir la
 * degradación de latencia cuando la cola de secuencias se llena.
 *
 * Metodología:
 *   1. Ejecutar contra un vLLM con MAX_NUM_SEQS_SERVER conocido.
 *   2. Forzar concurrencia al 50%, 100%, 150% y 200% de ese límite.
 *   3. Observar el "knee" en la curva P99 y la tasa de 429/503.
 *   4. Re-desplegar con distinto --max-num-seqs y comparar resultados.
 *
 * Re-despliegue con distinto max-num-seqs:
 *   helm upgrade vllm k8s/charts/vllm -n ai-platform \
 *     --set model.maxNumSeqs=128   # probar 64, 128, 256, 512
 *
 * Ejecución:
 *   k6 run \
 *     --env VLLM_URL=http://localhost:8000 \
 *     --env MAX_NUM_SEQS_SERVER=256 \
 *     --env PROM_URL=http://localhost:9090 \
 *     k6/scripts/max-concurrency-test.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Counter, Rate, Gauge } from 'k6/metrics';

const VLLM_URL          = __ENV.VLLM_URL           || 'http://localhost:8000';
const MODEL             = __ENV.MODEL               || 'qwen2.5-7b';
const PROM_URL          = __ENV.PROM_URL            || 'http://localhost:9090';
// Configura este valor igual que --max-num-seqs del servidor bajo prueba
const MAX_NUM_SEQS      = parseInt(__ENV.MAX_NUM_SEQS_SERVER || '256', 10);

// ── Métricas ───────────────────────────────────────────────────────────────
const reqLatency      = new Trend('concurrency_latency_ms', true);
const tokensPerSec    = new Trend('concurrency_tokens_per_sec', true);
const queueDepth      = new Gauge('vllm_queue_depth');
const runningSeqs     = new Gauge('vllm_running_seqs');
const rejectedReqs    = new Counter('concurrency_rejected');
const errorRate       = new Rate('error_rate');
const preemptions     = new Gauge('vllm_preemptions_total');

// ── Escenarios: 50% → 100% → 150% → 200% de MAX_NUM_SEQS ─────────────────
export const options = {
  scenarios: {
    half_capacity: {
      executor: 'constant-vus',
      vus: Math.max(1, Math.floor(MAX_NUM_SEQS * 0.5)),
      duration: '3m',
      startTime: '0s',
      tags: { phase: 'half' },
    },
    full_capacity: {
      executor: 'constant-vus',
      vus: MAX_NUM_SEQS,
      duration: '3m',
      startTime: '3m30s',
      tags: { phase: 'full' },
    },
    over_capacity: {
      executor: 'constant-vus',
      vus: Math.floor(MAX_NUM_SEQS * 1.5),
      duration: '3m',
      startTime: '7m',
      tags: { phase: 'over' },
    },
    double_capacity: {
      executor: 'constant-vus',
      vus: MAX_NUM_SEQS * 2,
      duration: '3m',
      startTime: '10m30s',
      tags: { phase: 'double' },
    },
  },

  thresholds: {
    // Al 50% de capacidad el sistema debe responder bien
    'concurrency_latency_ms{phase:half}':   ['p(99)<15000', 'p(50)<5000'],
    // Al 100% aceptamos algo de degradación
    'concurrency_latency_ms{phase:full}':   ['p(99)<30000'],
    // Por encima esperamos saturación — solo monitoreamos, sin umbral de fallo
    // Error rate global tolerable
    error_rate: ['rate<0.30'],
  },
};

// ── Prompts con longitudes variables para estresar el scheduler ────────────
const PROMPTS = [
  // Corto (~30 tokens output)
  'Lista tres documentos requeridos en una licitación pública.',
  // Medio (~100 tokens output)
  'Describe los criterios de evaluación técnica y financiera típicos en contratos públicos de tecnología.',
  // Largo (~250 tokens output)
  'Redacta un análisis detallado de los riesgos legales y financieros asociados a la participación en una licitación pública de suministro de equipamiento médico, incluyendo requisitos de certificación, garantías y penalizaciones por incumplimiento.',
];

function prompt() {
  return PROMPTS[(__VU + __ITER) % PROMPTS.length];
}

// ── Llamada a vLLM ─────────────────────────────────────────────────────────
function callVLLM() {
  const payload = JSON.stringify({
    model:       MODEL,
    prompt:      prompt(),
    max_tokens:  150,
    temperature: 0.0,
    stream:      false,
  });

  const start = Date.now();
  const res = http.post(`${VLLM_URL}/v1/completions`, payload, {
    headers: { 'Content-Type': 'application/json' },
    timeout: '120s',
  });
  const elapsed = Date.now() - start;

  const ok = check(res, {
    'status 200':   (r) => r.status === 200,
    'has choices':  (r) => {
      try { return JSON.parse(r.body).choices?.length > 0; }
      catch { return false; }
    },
  });

  if (res.status === 429 || res.status === 503) {
    rejectedReqs.add(1);
    errorRate.add(1);
  } else if (!ok) {
    errorRate.add(1);
  } else {
    errorRate.add(0);
    reqLatency.add(elapsed);
    try {
      const body = JSON.parse(res.body);
      const tokens = body.usage?.completion_tokens || 0;
      if (tokens > 0) tokensPerSec.add(tokens / (elapsed / 1000));
    } catch { /* ignorar */ }
  }
}

// ── Métricas internas de vLLM via Prometheus ──────────────────────────────
function pollVLLMMetrics() {
  const queries = {
    queue:       'vllm:num_requests_waiting',
    running:     'vllm:num_requests_running',
    preempt:     'vllm:num_preemptions_total',
  };

  for (const [key, q] of Object.entries(queries)) {
    const res = http.get(
      `${PROM_URL}/api/v1/query?query=${encodeURIComponent(q)}`,
      { timeout: '3s', tags: { endpoint: 'prometheus' } }
    );
    if (res.status !== 200) continue;
    try {
      const data = JSON.parse(res.body);
      const val  = parseFloat(data?.data?.result?.[0]?.value?.[1] || '0');
      if (!isNaN(val)) {
        if (key === 'queue')   queueDepth.add(val);
        if (key === 'running') runningSeqs.add(val);
        if (key === 'preempt') preemptions.add(val);
      }
    } catch { /* ignorar */ }
  }
}

// ── VU principal ───────────────────────────────────────────────────────────
export default function () {
  group('inference', () => callVLLM());

  // Poll métricas cada 10 iteraciones por VU para no saturar Prometheus
  if (__ITER % 10 === 0) pollVLLMMetrics();
}

// ── Resumen ────────────────────────────────────────────────────────────────
export function handleSummary(data) {
  const phases = ['half', 'full', 'over', 'double'];
  const vus    = {
    half:   Math.floor(MAX_NUM_SEQS * 0.5),
    full:   MAX_NUM_SEQS,
    over:   Math.floor(MAX_NUM_SEQS * 1.5),
    double: MAX_NUM_SEQS * 2,
  };

  function stat(phase, percentile) {
    const key = `concurrency_latency_ms{phase:${phase}}`;
    const val = data.metrics[key]?.values?.[percentile] || 0;
    return String(val.toFixed(0)).padStart(9);
  }

  function tps(phase) {
    const key = `concurrency_tokens_per_sec{phase:${phase}}`;
    const val = data.metrics[key]?.values?.avg || 0;
    return String(val.toFixed(1)).padStart(8);
  }

  const rejected  = data.metrics.concurrency_rejected?.values?.count || 0;
  const errRate   = (data.metrics.error_rate?.values?.rate || 0) * 100;
  const maxQueue  = data.metrics.vllm_queue_depth?.values?.max || 0;
  const maxPreempt= data.metrics.vllm_preemptions_total?.values?.max || 0;

  let rows = '';
  for (const p of phases) {
    const load = ((vus[p] / MAX_NUM_SEQS) * 100).toFixed(0) + '%';
    rows += `║  ${p.padEnd(6)} │ ${String(vus[p]).padStart(5)} VUs (${load.padStart(4)}) │${stat(p,'med')} ms │${stat(p,'p(90)')} ms │${stat(p,'p(99)')} ms │${tps(p)} t/s ║\n`;
  }

  const report = `
╔══════════════════════════════════════════════════════════════════════════════════╗
║          MAX MODEL CONCURRENCY EXPERIMENT — vLLM (max-num-seqs=${MAX_NUM_SEQS})            ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║  Phase  │  Carga             │  P50 (ms) │  P90 (ms) │  P99 (ms) │  Tok/s    ║
╠══════════════════════════════════════════════════════════════════════════════════╣
${rows}╠══════════════════════════════════════════════════════════════════════════════════╣
║  DIAGNÓSTICO                                                                     ║
║    Requests rechazados (429/503): ${String(rejected).padEnd(10)}                               ║
║    Tasa de error global:          ${errRate.toFixed(2).padEnd(10)}%                              ║
║    Profundidad máx. de cola:      ${String(maxQueue).padEnd(10)}                               ║
║    Preemptions totales:           ${String(maxPreempt).padEnd(10)}                               ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║  INTERPRETACIÓN                                                                  ║
║    • Si P99 sube bruscamente en "over"/"double": el scheduler está saturado.     ║
║    • Muchos preemptions → fragmentación de KV cache bajo alta concurrencia.      ║
║    • Ajuste: re-desplegar con max-num-seqs diferente y comparar tablas.          ║
║      helm upgrade vllm k8s/charts/vllm -n ai-platform --set model.maxNumSeqs=N  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
`;

  return {
    stdout: report,
    'k6/results/max_concurrency.json': JSON.stringify(data, null, 2),
  };
}