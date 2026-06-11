/**
 * K6 Benchmark Suite — Procurement Intelligence Platform
 * Tests: simple / medium / complex queries
 * Reports: retrieval time, LLM time (estimated), total time
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://backend:8000';
const TENDER_ID = __ENV.TENDER_ID || '00000000-0000-0000-0000-000000000003';

const simpleLatency  = new Trend('benchmark_simple_ms',  true);
const mediumLatency  = new Trend('benchmark_medium_ms',  true);
const complexLatency = new Trend('benchmark_complex_ms', true);

export const options = {
  scenarios: {
    benchmark: {
      executor: 'per-vu-iterations',
      vus: 1,
      iterations: 5,
      maxDuration: '30m',
    },
  },
};

const SIMPLE_QUERIES = [
  'Cual es la fecha limite?',
  'Que tipo de garantia se requiere?',
];

const MEDIUM_QUERIES = [
  'Cuales son todos los documentos obligatorios para participar en esta licitacion?',
  'Describe los requisitos financieros y legales de la licitacion.',
];

const COMPLEX_QUERIES = [
  'Analiza todos los requisitos de la licitacion, identifica los documentos criticos, las fechas importantes y las restricciones de participacion, y evalua el riesgo de incumplimiento.',
  'Proporciona un analisis completo de los criterios de evaluacion, penalidades por incumplimiento, presupuesto disponible y plazo de presentacion de esta licitacion publica.',
];

function query(question, top_k = 5) {
  return http.post(
    `${BASE_URL}/api/v1/rag/query`,
    JSON.stringify({ question, tender_id: TENDER_ID, top_k }),
    { headers: { 'Content-Type': 'application/json' }, timeout: '120s' }
  );
}

export default function () {
  console.log(`\n=== BENCHMARK ITERATION ${__ITER + 1} ===`);

  // Simple queries
  for (const q of SIMPLE_QUERIES) {
    const res = query(q, 3);
    const ok = check(res, { 'simple 200': (r) => r.status === 200 });
    if (ok) simpleLatency.add(res.timings.duration);
    console.log(`[SIMPLE]  ${q.slice(0,40)}: ${res.timings.duration.toFixed(0)}ms`);
    sleep(1);
  }

  // Medium queries
  for (const q of MEDIUM_QUERIES) {
    const res = query(q, 5);
    const ok = check(res, { 'medium 200': (r) => r.status === 200 });
    if (ok) mediumLatency.add(res.timings.duration);
    console.log(`[MEDIUM]  ${q.slice(0,40)}: ${res.timings.duration.toFixed(0)}ms`);
    sleep(1);
  }

  // Complex queries
  for (const q of COMPLEX_QUERIES) {
    const res = query(q, 10);
    const ok = check(res, { 'complex 200': (r) => r.status === 200 });
    if (ok) complexLatency.add(res.timings.duration);
    console.log(`[COMPLEX] ${q.slice(0,40)}: ${res.timings.duration.toFixed(0)}ms`);
    sleep(2);
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const s = m.benchmark_simple_ms?.values || {};
  const med = m.benchmark_medium_ms?.values || {};
  const c = m.benchmark_complex_ms?.values || {};

  const report = `
╔══════════════════════════════════════════════════════════════╗
║         PROCUREMENT PLATFORM — BENCHMARK RESULTS             ║
╠══════════════════════════════════════════════════════════════╣
║  Query Type     │   P50 (ms)   │   P90 (ms)   │   Max (ms)  ║
╠══════════════════════════════════════════════════════════════╣
║  Simple         │ ${String((s.med||0).toFixed(0)).padEnd(12)} │ ${String((s['p(90)']||0).toFixed(0)).padEnd(12)} │ ${String((s.max||0).toFixed(0)).padEnd(11)}║
║  Medium         │ ${String((med.med||0).toFixed(0)).padEnd(12)} │ ${String((med['p(90)']||0).toFixed(0)).padEnd(12)} │ ${String((med.max||0).toFixed(0)).padEnd(11)}║
║  Complex        │ ${String((c.med||0).toFixed(0)).padEnd(12)} │ ${String((c['p(90)']||0).toFixed(0)).padEnd(12)} │ ${String((c.max||0).toFixed(0)).padEnd(11)}║
╚══════════════════════════════════════════════════════════════╝
`;
  return {
    stdout: report,
    '/tmp/benchmark_summary.json': JSON.stringify(data, null, 2),
  };
}
