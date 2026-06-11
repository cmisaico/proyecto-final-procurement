/**
 * K6 Speculative Decoding Experiment — vLLM (Qwen2.5-7B + ngram/draft)
 *
 * Objetivo: cuantificar la ganancia de speculative decoding en latencia
 * (especialmente TTFT y throughput total) comparada con el modo estándar.
 *
 * Modos de speculative decoding soportados por vLLM:
 *
 *   A) Ngram speculation (sin modelo extra, funciona con AWQ en T4):
 *      helm upgrade vllm k8s/charts/vllm -n ai-platform \
 *        --set speculative.enabled=true \
 *        --set speculative.draftModel="[ngram]" \
 *        --set speculative.numSpeculativeTokens=5 \
 *        --set speculative.ngramPromptLookupMin=4 \
 *        --set speculative.ngramPromptLookupMax=8
 *
 *   B) Draft model (Qwen2.5-0.5B, requiere ~1 GB VRAM adicional):
 *      helm upgrade vllm k8s/charts/vllm -n ai-platform \
 *        --set speculative.enabled=true \
 *        --set 'speculative.draftModel=Qwen/Qwen2.5-0.5B-Instruct-AWQ' \
 *        --set speculative.numSpeculativeTokens=5
 *
 * Metodología del experimento:
 *   Fase 1 (BASELINE)   — vLLM sin speculative decoding.
 *   Fase 2 (SPECULATIVE) — Mismo vLLM con speculative habilitado.
 *   Las métricas de vLLM (TTFT, acceptance rate) se leen desde Prometheus
 *   antes y después de cada fase para capturar el delta real del servidor.
 *
 * Ejecución — Fase 1:
 *   helm upgrade vllm k8s/charts/vllm -n ai-platform --set speculative.enabled=false
 *   k6 run --env VLLM_URL=http://... --env PHASE=baseline k6/scripts/speculative-decoding-test.js
 *
 * Ejecución — Fase 2 (después de re-desplegar con speculative.enabled=true):
 *   k6 run --env VLLM_URL=http://... --env PHASE=speculative k6/scripts/speculative-decoding-test.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Counter, Rate, Gauge } from 'k6/metrics';

const VLLM_URL  = __ENV.VLLM_URL  || 'http://localhost:8000';
const MODEL     = __ENV.MODEL     || 'qwen2.5-7b';
const PROM_URL  = __ENV.PROM_URL  || 'http://localhost:9090';
// "baseline" o "speculative" — etiqueta el reporte para comparar ambas corridas
const PHASE     = __ENV.PHASE     || 'baseline';

// ── Métricas ───────────────────────────────────────────────────────────────
const reqLatency       = new Trend('spec_latency_ms', true);
const tokensPerSec     = new Trend('spec_tokens_per_sec', true);
// TTFT aproximado: tiempo hasta el primer token en modo no-streaming.
// En modo stream:false, refleja el tiempo de prefill + draft acceptance.
const ttftProxy        = new Trend('spec_ttft_proxy_ms', true);
const acceptanceRate   = new Gauge('spec_draft_acceptance_rate');
const serverTTFT_p50   = new Gauge('spec_server_ttft_p50_ms');
const serverTTFT_p99   = new Gauge('spec_server_ttft_p99_ms');
const errorRate        = new Rate('error_rate');
const totalTokens      = new Counter('spec_total_tokens');

// ── Escenario ──────────────────────────────────────────────────────────────
export const options = {
  scenarios: {
    speculative_test: {
      executor: 'constant-vus',
      // 16 VUs: presión moderada que permite medir el beneficio de spec decoding
      vus: 16,
      duration: '10m',
      tags: { phase: PHASE },
    },
  },
  thresholds: {
    // Umbrales iguales para ambas fases — la fase speculative debe superarlos
    'spec_latency_ms':   ['p(99)<20000', 'p(50)<8000'],
    'error_rate':        ['rate<0.05'],
  },
};

// ── Prompts: elegidos por ser repetitivos/formulaicos (ideal para ngram) ──
// Speculative decoding gana más en texto formulaico y con patrones repetidos,
// típico en análisis de documentos de licitación.
const PROMPTS = [
  // Formulaico — alta repetición, ideal para ngram speculation
  {
    text: 'Completa el siguiente formulario de licitación: Empresa: ___, NIF: ___, Fecha: ___, Oferta económica: ___, Plazo de entrega: ___, Garantía: ___, Firma: ___',
    label: 'formulaic',
    maxTokens: 200,
  },
  // Extractivo — el modelo copia fragmentos del prompt (alta aceptación ngram)
  {
    text: 'Extrae y lista textualmente los plazos mencionados en: "El plazo de presentación finaliza el 30 de junio. El plazo de ejecución es de 12 meses. El plazo de garantía es de 24 meses. El plazo de subsanación de defectos es de 30 días."',
    label: 'extractive',
    maxTokens: 150,
  },
  // Resumen estructurado — semi-formulaico
  {
    text: 'Genera un resumen ejecutivo de licitación con las siguientes secciones: 1. Objeto del contrato, 2. Presupuesto base de licitación, 3. Criterios de adjudicación, 4. Requisitos de solvencia, 5. Plazo de presentación de ofertas.',
    label: 'structured',
    maxTokens: 300,
  },
  // Creativo — baja repetición (peor caso para speculative decoding)
  {
    text: 'Redacta una propuesta innovadora para digitalizar el proceso de contratación pública usando inteligencia artificial, blockchain y automatización de flujos de trabajo.',
    label: 'creative',
    maxTokens: 350,
  },
  // Conversacional — neutral
  {
    text: '¿Cuáles son los pasos para presentar una reclamación tras la resolución de adjudicación en una licitación pública española?',
    label: 'qa',
    maxTokens: 200,
  },
];

function selectPrompt() {
  return PROMPTS[(__VU + __ITER) % PROMPTS.length];
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
    tags:    { prompt_type: label, phase: PHASE },
    timeout: '60s',
  });
  const elapsed = Date.now() - start;

  const ok = check(res, {
    'status 200':  (r) => r.status === 200,
    'has choices': (r) => {
      try { return JSON.parse(r.body).choices?.length > 0; }
      catch { return false; }
    },
  });

  if (!ok) {
    errorRate.add(1);
    return;
  }

  errorRate.add(0);
  reqLatency.add(elapsed, { prompt_type: label });

  try {
    const body   = JSON.parse(res.body);
    const usage  = body.usage || {};
    const tokens = usage.completion_tokens || 0;
    const prompt_tokens = usage.prompt_tokens || 1;

    if (tokens > 0) {
      const secs = elapsed / 1000;
      tokensPerSec.add(tokens / secs, { prompt_type: label });
      totalTokens.add(tokens);
      // TTFT proxy: tiempo de prefill estimado = elapsed * (prompt_tokens / total_tokens)
      // Aproximación: el prefill domina cuando prompt >> completion
      const ttftEstimate = elapsed * (prompt_tokens / (prompt_tokens + tokens));
      ttftProxy.add(ttftEstimate, { prompt_type: label });
    }
  } catch { /* ignorar */ }
}

// ── Métricas del servidor vLLM via Prometheus ─────────────────────────────
function pollServerMetrics() {
  // Acceptance rate: solo existe cuando speculative decoding está habilitado
  const acceptQuery = 'vllm:spec_decode_draft_acceptance_rate';
  const ttftP50Query = 'histogram_quantile(0.50, rate(vllm:time_to_first_token_seconds_bucket[2m]))';
  const ttftP99Query = 'histogram_quantile(0.99, rate(vllm:time_to_first_token_seconds_bucket[2m]))';

  for (const [label, query] of [
    ['acceptance', acceptQuery],
    ['ttft_p50',   ttftP50Query],
    ['ttft_p99',   ttftP99Query],
  ]) {
    const res = http.get(
      `${PROM_URL}/api/v1/query?query=${encodeURIComponent(query)}`,
      { timeout: '3s', tags: { endpoint: 'prometheus' } }
    );
    if (res.status !== 200) continue;
    try {
      const val = parseFloat(
        JSON.parse(res.body)?.data?.result?.[0]?.value?.[1] || '0'
      );
      if (isNaN(val)) continue;
      if (label === 'acceptance') acceptanceRate.add(val * 100);
      if (label === 'ttft_p50')   serverTTFT_p50.add(val * 1000); // s → ms
      if (label === 'ttft_p99')   serverTTFT_p99.add(val * 1000);
    } catch { /* ignorar */ }
  }
}

// ── VU principal ───────────────────────────────────────────────────────────
export default function () {
  group('inference', () => callVLLM());
  if (__ITER % 10 === 0) pollServerMetrics();
}

// ── Resumen ────────────────────────────────────────────────────────────────
export function handleSummary(data) {
  const m = data.metrics;

  function latByType(label, p) {
    const key = `spec_latency_ms{prompt_type:${label}}`;
    const val = data.metrics[key]?.values?.[p] || 0;
    return String(val.toFixed(0)).padStart(9);
  }
  function tpsByType(label) {
    const key = `spec_tokens_per_sec{prompt_type:${label}}`;
    const val = data.metrics[key]?.values?.avg || 0;
    return String(val.toFixed(1)).padStart(7);
  }

  const overallLat  = m.spec_latency_ms?.values || {};
  const overallTPS  = m.spec_tokens_per_sec?.values || {};
  const ttfxP50     = m.spec_ttft_proxy_ms?.values?.['p(50)'] || 0;
  const ttfxP99     = m.spec_ttft_proxy_ms?.values?.['p(99)'] || 0;
  const acceptance  = m.spec_draft_acceptance_rate?.values?.avg || 0;
  const srvTTFTp50  = m.spec_server_ttft_p50_ms?.values?.avg || 0;
  const srvTTFTp99  = m.spec_server_ttft_p99_ms?.values?.avg || 0;
  const totalTok    = m.spec_total_tokens?.values?.count || 0;
  const errRate     = (m.error_rate?.values?.rate || 0) * 100;

  const phaseLabel = PHASE === 'speculative' ? 'SPECULATIVE DECODING ENABLED' : 'BASELINE (sin speculative)';

  const report = `
╔═══════════════════════════════════════════════════════════════════════════════╗
║         SPECULATIVE DECODING EXPERIMENT — ${phaseLabel.padEnd(34)}║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  Latencia por tipo de prompt                                                  ║
║  Tipo        │  P50 (ms) │  P90 (ms) │  P99 (ms) │  Tok/s                    ║
║  ────────────┼───────────┼───────────┼───────────┼────────                    ║
║  formulaic   │${latByType('formulaic','med')} ms │${latByType('formulaic','p(90)')} ms │${latByType('formulaic','p(99)')} ms │${tpsByType('formulaic')} t/s ║
║  extractive  │${latByType('extractive','med')} ms │${latByType('extractive','p(90)')} ms │${latByType('extractive','p(99)')} ms │${tpsByType('extractive')} t/s ║
║  structured  │${latByType('structured','med')} ms │${latByType('structured','p(90)')} ms │${latByType('structured','p(99)')} ms │${tpsByType('structured')} t/s ║
║  creative    │${latByType('creative','med')} ms │${latByType('creative','p(90)')} ms │${latByType('creative','p(99)')} ms │${tpsByType('creative')} t/s ║
║  qa          │${latByType('qa','med')} ms │${latByType('qa','p(90)')} ms │${latByType('qa','p(99)')} ms │${tpsByType('qa')} t/s ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  MÉTRICAS GLOBALES                                                            ║
║    Latencia total  P50: ${String((overallLat.med||0).toFixed(0)).padEnd(8)} ms   P99: ${String((overallLat['p(99)']||0).toFixed(0)).padEnd(8)} ms              ║
║    Throughput avg: ${String((overallTPS.avg||0).toFixed(1)).padEnd(8)} t/s  max: ${String((overallTPS.max||0).toFixed(1)).padEnd(8)} t/s              ║
║    Tokens totales: ${String(totalTok).padEnd(10)}                                            ║
║    Tasa de error:  ${errRate.toFixed(2).padEnd(8)} %                                         ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  MÉTRICAS DE SPECULATIVE DECODING (desde Prometheus)                          ║
║    Draft acceptance rate:  ${String(acceptance.toFixed(1)).padEnd(8)} %  (0% = baseline, >50% = bueno)     ║
║    TTFT P50 (servidor):    ${String(srvTTFTp50.toFixed(0)).padEnd(8)} ms                                   ║
║    TTFT P99 (servidor):    ${String(srvTTFTp99.toFixed(0)).padEnd(8)} ms                                   ║
║    TTFT proxy P50 (k6):    ${String(ttfxP50.toFixed(0)).padEnd(8)} ms                                   ║
║    TTFT proxy P99 (k6):    ${String(ttfxP99.toFixed(0)).padEnd(8)} ms                                   ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  INTERPRETACIÓN                                                               ║
║    • Acceptance rate > 70%: ngram/draft funciona bien para este dominio.      ║
║    • Acceptance rate < 30%: texto demasiado variable; spec decoding no ayuda. ║
║    • Comparar TTFT P50 baseline vs speculative: la ganancia esperada es       ║
║      10-40% en prompts formulaicos/extractivos de documentos de licitación.   ║
║    • Si creative/qa no mejoran, es normal: son los peores casos para spec.    ║
╚═══════════════════════════════════════════════════════════════════════════════╝
`;

  return {
    stdout: report,
    [`k6/results/speculative_decoding_${PHASE}.json`]: JSON.stringify(data, null, 2),
  };
}