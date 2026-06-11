/**
 * K6 Benchmark Suite — Kubernetes Deployment (Fase 4)
 * Tests against vLLM (GPU) instead of Ollama (CPU)
 * Scenarios: 10 / 50 / 100 / 200 concurrent users
 * Measures: P50, P90, P99, throughput, tokens/s
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Rate, Trend, Gauge } from 'k6/metrics';

const BASE_URL  = __ENV.BASE_URL  || 'http://procurement.local';
const VLLM_URL  = __ENV.VLLM_URL  || 'http://localhost:8000';
const TENDER_ID = __ENV.TENDER_ID || '00000000-0000-0000-0000-000000000003';

// ── Custom metrics ─────────────────────────────────────────────────────────
const ragDuration    = new Trend('rag_duration_ms',  true);
const vllmTokenRate  = new Trend('vllm_tokens_per_sec', true);
const ragErrors      = new Counter('rag_errors');
const errorRate      = new Rate('error_rate');
const activeRequests = new Gauge('active_requests');

// ── Scenarios ──────────────────────────────────────────────────────────────
export const options = {
  scenarios: {
    light_10: {
      executor: 'constant-vus',
      vus: 10,
      duration: '2m',
      startTime: '0s',
      tags: { scenario: '10_users' },
    },
    medium_50: {
      executor: 'constant-vus',
      vus: 50,
      duration: '3m',
      startTime: '2m30s',
      tags: { scenario: '50_users' },
    },
    heavy_100: {
      executor: 'constant-vus',
      vus: 100,
      duration: '3m',
      startTime: '6m',
      tags: { scenario: '100_users' },
    },
    stress_200: {
      executor: 'constant-vus',
      vus: 200,
      duration: '2m',
      startTime: '10m',
      tags: { scenario: '200_users' },
    },
  },

  thresholds: {
    // vLLM GPU target: P99 < 15s (vs 60s with CPU Ollama)
    'rag_duration_ms{scenario:10_users}':  ['p(99)<15000'],
    'rag_duration_ms{scenario:50_users}':  ['p(99)<20000'],
    'rag_duration_ms{scenario:100_users}': ['p(99)<30000'],
    'rag_duration_ms{scenario:200_users}': ['p(99)<60000'],
    // Overall error rate < 2%
    error_rate:                            ['rate<0.02'],
    // Health checks fast
    'http_req_duration{endpoint:health}':  ['p(99)<500'],
  },
};

const SIMPLE_QUESTIONS = [
  'Cual es la fecha limite de presentacion?',
  'Que tipo de garantia se requiere?',
  'Cual es el plazo de entrega?',
];

const MEDIUM_QUESTIONS = [
  'Cuales son todos los documentos obligatorios para participar en esta licitacion?',
  'Describe los requisitos financieros y legales de la licitacion.',
  'Cuales son los criterios de evaluacion de propuestas?',
];

const COMPLEX_QUESTIONS = [
  'Analiza todos los requisitos de la licitacion, identifica los documentos criticos, las fechas importantes y las restricciones de participacion, y evalua el riesgo de incumplimiento.',
  'Proporciona un analisis completo de los criterios de evaluacion, penalidades por incumplimiento, presupuesto disponible y plazo de presentacion de esta licitacion publica.',
];

function rand(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// ── Utility functions ──────────────────────────────────────────────────────
function ragQuery(question, topK = 5) {
  const start = Date.now();
  activeRequests.add(1);

  const res = http.post(
    `${BASE_URL}/api/v1/rag/query`,
    JSON.stringify({ question, tender_id: TENDER_ID, top_k: topK }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { endpoint: 'rag' },
      timeout: '60s',
    }
  );

  activeRequests.add(-1);
  const duration = Date.now() - start;

  const ok = check(res, {
    'rag status 200':  (r) => r.status === 200,
    'rag has answer':  (r) => {
      try { return JSON.parse(r.body).answer !== undefined; }
      catch { return false; }
    },
  });

  ragDuration.add(res.timings.duration);
  if (!ok) {
    ragErrors.add(1);
    errorRate.add(1);
  } else {
    errorRate.add(0);
    // Estimate tokens/s from vLLM headers (if present)
    const tokensHeader = res.headers['X-Completion-Tokens'];
    if (tokensHeader) {
      const tokens = parseInt(tokensHeader, 10);
      const secs = duration / 1000;
      if (secs > 0) vllmTokenRate.add(tokens / secs);
    }
  }
  return res;
}

function healthCheck() {
  const res = http.get(`${BASE_URL}/api/v1/health`, {
    tags: { endpoint: 'health' },
  });
  check(res, { 'health 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200 ? 1 : 0);
}

function statusCheck() {
  const res = http.get(`${BASE_URL}/api/v1/status`, {
    tags: { endpoint: 'status' },
  });
  check(res, { 'status healthy': (r) => {
    try { return JSON.parse(r.body).status === 'healthy'; }
    catch { return false; }
  }});
}

// ── Main VU function ───────────────────────────────────────────────────────
export default function () {
  const roll = Math.random();

  if (roll < 0.55) {
    group('rag_query', () => {
      // Distribution: 40% simple, 40% medium, 20% complex
      const type = Math.random();
      if (type < 0.40) {
        ragQuery(rand(SIMPLE_QUESTIONS), 3);
      } else if (type < 0.80) {
        ragQuery(rand(MEDIUM_QUESTIONS), 5);
      } else {
        ragQuery(rand(COMPLEX_QUESTIONS), 10);
      }
    });
  } else if (roll < 0.80) {
    group('health_check', () => healthCheck());
  } else {
    group('status_check', () => statusCheck());
  }

  sleep(Math.random() * 2 + 0.5);
}

// ── Summary ────────────────────────────────────────────────────────────────
export function handleSummary(data) {
  const m = data.metrics;
  const rag = m.rag_duration_ms?.values || {};
  const tps = m.vllm_tokens_per_sec?.values || {};
  const err = m.error_rate?.values || {};

  const report = `
╔══════════════════════════════════════════════════════════════════════╗
║     PROCUREMENT PLATFORM — K8s LOAD TEST (vLLM + RTX 5080)          ║
╠══════════════════════════════════════════════════════════════════════╣
║  Scenario        │  P50 (ms)  │  P90 (ms)  │  P99 (ms)  │  Max     ║
╠══════════════════════════════════════════════════════════════════════╣
║  10 users        │ ${scenarioStat(data, '10_users', 'p(50)')}        │ ${scenarioStat(data, '10_users', 'p(90)')}        │ ${scenarioStat(data, '10_users', 'p(99)')}        │ ${scenarioStat(data, '10_users', 'max')}   ║
║  50 users        │ ${scenarioStat(data, '50_users', 'p(50)')}        │ ${scenarioStat(data, '50_users', 'p(90)')}        │ ${scenarioStat(data, '50_users', 'p(99)')}        │ ${scenarioStat(data, '50_users', 'max')}   ║
║  100 users       │ ${scenarioStat(data, '100_users', 'p(50)')}        │ ${scenarioStat(data, '100_users', 'p(90)')}        │ ${scenarioStat(data, '100_users', 'p(99)')}        │ ${scenarioStat(data, '100_users', 'max')}   ║
║  200 users       │ ${scenarioStat(data, '200_users', 'p(50)')}        │ ${scenarioStat(data, '200_users', 'p(90)')}        │ ${scenarioStat(data, '200_users', 'p(99)')}        │ ${scenarioStat(data, '200_users', 'max')}   ║
╠══════════════════════════════════════════════════════════════════════╣
║  Overall RAG                                                         ║
║    P50: ${String((rag.med||0).toFixed(0)).padEnd(8)} ms    P90: ${String((rag['p(90)']||0).toFixed(0)).padEnd(8)} ms    P99: ${String((rag['p(99)']||0).toFixed(0)).padEnd(8)} ms             ║
║    Max: ${String((rag.max||0).toFixed(0)).padEnd(8)} ms    Error rate: ${((err.rate||0)*100).toFixed(2).padEnd(6)}%                       ║
╠══════════════════════════════════════════════════════════════════════╣
║  vLLM Throughput                                                     ║
║    Avg tokens/s: ${String((tps.avg||0).toFixed(1)).padEnd(8)}   Max tokens/s: ${String((tps.max||0).toFixed(1)).padEnd(8)}                  ║
║    Total requests: ${String(m.http_reqs?.values?.count||0).padEnd(8)}  Rate: ${((m.http_reqs?.values?.rate||0)).toFixed(2).padEnd(8)} req/s             ║
╚══════════════════════════════════════════════════════════════════════╝
`;
  return {
    stdout: report,
    'k6/results/k8s_load_test.json': JSON.stringify(data, null, 2),
  };
}

function scenarioStat(data, scenario, stat) {
  const key = `rag_duration_ms{scenario:${scenario}}`;
  const val = data.metrics[key]?.values?.[stat] || 0;
  return String(val.toFixed(0)).padEnd(10);
}
