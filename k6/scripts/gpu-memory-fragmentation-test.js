/**
 * K6 GPU Memory Fragmentation Experiment — vLLM (Qwen2.5-7B)
 *
 * Objetivo: medir la fragmentación del KV cache de la GPU bajo carga sostenida
 * con prompts de longitud muy variable, y comparar el comportamiento entre
 * distintos valores de --gpu-memory-utilization.
 *
 * Mecanismo de fragmentación:
 *   vLLM asigna bloques de KV cache de tamaño fijo (block_size=16 tokens).
 *   Prompts muy cortos dejan bloques parcialmente vacíos. Prompts muy largos
 *   causan preemptions cuando la memoria se agota. La mezcla aleatoria de
 *   ambos crea huecos no reutilizables → fragmentación.
 *
 * Indicadores medidos via Prometheus:
 *   - vllm:gpu_cache_usage_perc      — % de bloques KV en uso
 *   - vllm:num_preemptions_total     — secuencias expulsadas por falta de memoria
 *   - DCGM_FI_DEV_FB_USED           — VRAM física ocupada (MB)
 *   - DCGM_FI_DEV_FB_FREE           — VRAM física libre (MB)
 *
 * Comparar ejecuciones con:
 *   helm upgrade vllm k8s/charts/vllm -n ai-platform \
 *     --set model.gpuMemoryUtilization=0.70   # baseline conservador
 *     --set model.gpuMemoryUtilization=0.85   # actual (producción)
 *     --set model.gpuMemoryUtilization=0.95   # agresivo
 *
 * Ejecución:
 *   k6 run \
 *     --env VLLM_URL=http://localhost:8000 \
 *     --env PROM_URL=http://localhost:9090 \
 *     --env GPU_MEM_UTIL=0.85 \
 *     k6/scripts/gpu-memory-fragmentation-test.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Counter, Rate, Gauge } from 'k6/metrics';

const VLLM_URL   = __ENV.VLLM_URL    || 'http://localhost:8000';
const MODEL      = __ENV.MODEL        || 'qwen2.5-7b';
const PROM_URL   = __ENV.PROM_URL    || 'http://localhost:9090';
const GPU_UTIL   = __ENV.GPU_MEM_UTIL || '0.85'; // solo para etiquetar el reporte

// ── Métricas ───────────────────────────────────────────────────────────────
const reqLatency      = new Trend('frag_latency_ms', true);
const tokensPerSec    = new Trend('frag_tokens_per_sec', true);
const kvCacheUsage    = new Gauge('kv_cache_usage_pct');
const vramUsedMB      = new Gauge('gpu_vram_used_mb');
const vramFreeMB      = new Gauge('gpu_vram_free_mb');
const preemptionsGauge= new Gauge('kv_preemptions_total');
const waitingReqs     = new Gauge('vllm_waiting_reqs');
const errorRate       = new Rate('error_rate');
const rejectedReqs    = new Counter('frag_rejected');

// ── Escenario de larga duración con mezcla de longitudes ──────────────────
// 20 min para observar acumulación de fragmentación en el tiempo.
export const options = {
  scenarios: {
    fragmentation_load: {
      executor: 'constant-vus',
      // 32 VUs: suficiente para saturar el KV cache con la mezcla de longitudes
      vus: 32,
      duration: '20m',
    },
  },
  thresholds: {
    // La fragmentación no debería disparar el error rate
    error_rate: ['rate<0.10'],
    // P99 tolerable en condiciones de estrés
    frag_latency_ms: ['p(99)<60000'],
  },
};

// ── Prompts diseñados para maximizar fragmentación ─────────────────────────
// La clave es la alta varianza: mezcla de prompts muy cortos y muy largos
// en la misma ventana de tiempo, creando bloques KV de tamaños heterogéneos.
const FRAGMENTATION_PROMPTS = [
  // Extremadamente corto — ~10 tokens output, deja bloques casi vacíos
  { text: 'Di "sí" o "no": ¿es la fecha límite obligatoria?', maxTokens: 15, label: 'tiny' },
  { text: '¿Cuántos proveedores pueden participar?', maxTokens: 20, label: 'tiny' },

  // Corto — ~50 tokens output
  { text: '¿Cuáles son los documentos obligatorios para licitar?', maxTokens: 60, label: 'short' },
  { text: 'Resume en dos líneas los criterios de evaluación.', maxTokens: 60, label: 'short' },

  // Medio — ~150 tokens output
  { text: 'Describe los requisitos técnicos y financieros de una licitación pública de TI.', maxTokens: 180, label: 'medium' },
  { text: 'Explica el proceso de evaluación de ofertas en compras públicas con criterios de desempate.', maxTokens: 180, label: 'medium' },

  // Largo — ~400 tokens output, ocupa muchos bloques KV
  {
    text: 'Redacta un análisis exhaustivo de riesgos para una empresa que participa por primera vez en una licitación pública de suministro de equipamiento hospitalario en España. Incluye riesgos legales, financieros, operativos y reputacionales, con una estrategia de mitigación para cada uno.',
    maxTokens: 450,
    label: 'long',
  },
  {
    text: 'Genera un checklist completo de documentación requerida para participar en una licitación pública de servicios de consultoría tecnológica, incluyendo certificados de estar al corriente con Hacienda y Seguridad Social, capacidad técnica demostrable, referencias de proyectos similares, y propuesta económica detallada.',
    maxTokens: 500,
    label: 'long',
  },

  // Extremadamente largo — ~800 tokens output, máxima presión sobre bloques KV
  {
    text: 'Elabora un informe técnico completo sobre las mejores prácticas en gestión de contratos públicos de transformación digital, cubriendo: (1) marco normativo europeo y nacional, (2) criterios de adjudicación basados en la oferta económicamente más ventajosa, (3) gestión de riesgos en proyectos de múltiples años, (4) métricas de seguimiento y KPIs de rendimiento, (5) protocolos de modificación contractual y extensiones, y (6) buenas prácticas de transparencia y publicación de resultados. Proporciona ejemplos concretos para cada sección.',
    maxTokens: 850,
    label: 'huge',
  },
];

// Distribución de longitudes diseñada para máxima fragmentación:
// 20% tiny, 25% short, 25% medium, 25% long, 5% huge
const WEIGHTS = [
  ...Array(4).fill(0), ...Array(4).fill(1),   // tiny (idx 0,1)
  ...Array(5).fill(2), ...Array(5).fill(3),   // short (idx 2,3)
  ...Array(5).fill(4), ...Array(5).fill(5),   // medium (idx 4,5)
  ...Array(5).fill(6), ...Array(5).fill(7),   // long (idx 6,7)
  ...Array(2).fill(8),                         // huge (idx 8)
];

function selectPrompt() {
  const idx = WEIGHTS[(__VU * 7 + __ITER * 13) % WEIGHTS.length];
  return FRAGMENTATION_PROMPTS[idx];
}

// ── Llamada a vLLM ─────────────────────────────────────────────────────────
function callVLLM() {
  const { text, maxTokens, label } = selectPrompt();
  const payload = JSON.stringify({
    model:       MODEL,
    prompt:      text,
    max_tokens:  maxTokens,
    temperature: 0.0,
    stream:      false,
  });

  const start = Date.now();
  const res = http.post(`${VLLM_URL}/v1/completions`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags:    { prompt_size: label },
    timeout: '120s',
  });
  const elapsed = Date.now() - start;

  const ok = check(res, {
    'status 200':  (r) => r.status === 200,
    'has choices': (r) => {
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
    reqLatency.add(elapsed, { prompt_size: label });
    try {
      const body   = JSON.parse(res.body);
      const tokens = body.usage?.completion_tokens || 0;
      if (tokens > 0) tokensPerSec.add(tokens / (elapsed / 1000), { prompt_size: label });
    } catch { /* ignorar */ }
  }
}

// ── Poll de métricas de fragmentación ─────────────────────────────────────
function pollFragmentationMetrics() {
  const queries = {
    kv_cache:   'vllm:gpu_cache_usage_perc',
    preempts:   'vllm:num_preemptions_total',
    waiting:    'vllm:num_requests_waiting',
    vram_used:  'DCGM_FI_DEV_FB_USED',
    vram_free:  'DCGM_FI_DEV_FB_FREE',
  };

  for (const [key, q] of Object.entries(queries)) {
    const res = http.get(
      `${PROM_URL}/api/v1/query?query=${encodeURIComponent(q)}`,
      { timeout: '3s', tags: { endpoint: 'prometheus' } }
    );
    if (res.status !== 200) continue;
    try {
      const val = parseFloat(
        JSON.parse(res.body)?.data?.result?.[0]?.value?.[1] || '0'
      );
      if (isNaN(val)) continue;
      if (key === 'kv_cache')  kvCacheUsage.add(val * 100); // Prometheus da 0-1
      if (key === 'preempts')  preemptionsGauge.add(val);
      if (key === 'waiting')   waitingReqs.add(val);
      if (key === 'vram_used') vramUsedMB.add(val);
      if (key === 'vram_free') vramFreeMB.add(val);
    } catch { /* ignorar */ }
  }
}

// ── VU principal ───────────────────────────────────────────────────────────
export default function () {
  group('inference', () => callVLLM());

  // Muestrear métricas de fragmentación cada 8 iteraciones
  if (__ITER % 8 === 0) pollFragmentationMetrics();
}

// ── Resumen ────────────────────────────────────────────────────────────────
export function handleSummary(data) {
  const m = data.metrics;

  function latStat(label, p) {
    const key = `frag_latency_ms{prompt_size:${label}}`;
    const val = data.metrics[key]?.values?.[p] || 0;
    return String(val.toFixed(0)).padStart(9);
  }
  function tpsStat(label) {
    const key = `frag_tokens_per_sec{prompt_size:${label}}`;
    const val = data.metrics[key]?.values?.avg || 0;
    return String(val.toFixed(1)).padStart(7);
  }

  const kvMax      = m.kv_cache_usage_pct?.values?.max || 0;
  const kvAvg      = m.kv_cache_usage_pct?.values?.avg || 0;
  const preemptMax = m.kv_preemptions_total?.values?.max || 0;
  const vramUsed   = m.gpu_vram_used_mb?.values?.max || 0;
  const vramFree   = m.gpu_vram_free_mb?.values?.min || 0;
  const vramTotal  = vramUsed + vramFree;
  const fragRatio  = vramTotal > 0 ? ((vramFree / vramTotal) * 100).toFixed(1) : 'N/A';
  const rejected   = m.frag_rejected?.values?.count || 0;
  const errRate    = (m.error_rate?.values?.rate || 0) * 100;

  const report = `
╔═══════════════════════════════════════════════════════════════════════════════╗
║    GPU MEMORY FRAGMENTATION EXPERIMENT (gpu-memory-utilization=${GPU_UTIL})         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  Latencia por tamaño de prompt                                                ║
║  Tamaño  │  P50 (ms) │  P90 (ms) │  P99 (ms) │  Tok/s                        ║
║  ────────┼───────────┼───────────┼───────────┼────────                        ║
║  tiny    │${latStat('tiny','med')} ms │${latStat('tiny','p(90)')} ms │${latStat('tiny','p(99)')} ms │${tpsStat('tiny')} t/s  ║
║  short   │${latStat('short','med')} ms │${latStat('short','p(90)')} ms │${latStat('short','p(99)')} ms │${tpsStat('short')} t/s  ║
║  medium  │${latStat('medium','med')} ms │${latStat('medium','p(90)')} ms │${latStat('medium','p(99)')} ms │${tpsStat('medium')} t/s  ║
║  long    │${latStat('long','med')} ms │${latStat('long','p(90)')} ms │${latStat('long','p(99)')} ms │${tpsStat('long')} t/s  ║
║  huge    │${latStat('huge','med')} ms │${latStat('huge','p(90)')} ms │${latStat('huge','p(99)')} ms │${tpsStat('huge')} t/s  ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  MÉTRICAS DE FRAGMENTACIÓN DE KV CACHE                                        ║
║    Uso máx. KV cache:       ${String(kvMax.toFixed(1)).padEnd(10)} %                               ║
║    Uso prom. KV cache:      ${String(kvAvg.toFixed(1)).padEnd(10)} %                               ║
║    Preemptions totales:     ${String(preemptMax).padEnd(10)}                                   ║
║    VRAM usada (máx):        ${String(vramUsed.toFixed(0)).padEnd(10)} MB                              ║
║    VRAM libre (mín):        ${String(vramFree.toFixed(0)).padEnd(10)} MB                              ║
║    VRAM libre / total:      ${fragRatio.padEnd(10)} %  ← indicador de fragmentación        ║
║    Requests rechazados:     ${String(rejected).padEnd(10)}                                   ║
║    Tasa de error:           ${errRate.toFixed(2).padEnd(10)} %                               ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  INTERPRETACIÓN                                                               ║
║    • Preemptions > 0 → el KV cache se agota: bajar gpu-memory-utilization     ║
║      o reducir max-model-len para liberar bloques más rápido.                 ║
║    • VRAM libre / total > 20% con KV cache al 90%+ → fragmentación real.      ║
║    • Comparar con utilization=0.70 / 0.85 / 0.95 para encontrar el óptimo.   ║
╚═══════════════════════════════════════════════════════════════════════════════╝
`;

  return {
    stdout: report,
    'k6/results/gpu_fragmentation.json': JSON.stringify(data, null, 2),
  };
}