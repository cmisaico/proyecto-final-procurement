/**
 * K6 Load Test — Procurement Intelligence Platform
 * Scenarios: 10 / 50 / 100 concurrent users
 * Measures: P50, P90, P99, throughput, error rate
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://backend:8000';
const TENDER_ID = __ENV.TENDER_ID || '00000000-0000-0000-0000-000000000003';

// Custom metrics
const ragErrors    = new Counter('rag_errors');
const ragDuration  = new Trend('rag_duration_ms', true);
const errorRate    = new Rate('error_rate');

export const options = {
  scenarios: {
    light_load: {
      executor: 'constant-vus',
      vus: 10,
      duration: '1m',
      tags: { scenario: '10_users' },
    },
    medium_load: {
      executor: 'constant-vus',
      vus: 50,
      duration: '2m',
      startTime: '90s',
      tags: { scenario: '50_users' },
    },
    heavy_load: {
      executor: 'constant-vus',
      vus: 100,
      duration: '2m',
      startTime: '3m30s',
      tags: { scenario: '100_users' },
    },
  },
  thresholds: {
    // P99 of RAG queries must be under 60s
    'http_req_duration{endpoint:rag}': ['p(99)<60000'],
    // Error rate below 5%
    'error_rate':   ['rate<0.05'],
    // Health check P99 < 500ms
    'http_req_duration{endpoint:health}': ['p(99)<500'],
  },
};

const QUESTIONS = [
  'Cuales son los requisitos obligatorios?',
  'Cual es la fecha limite de presentacion?',
  'Que documentos se requieren?',
  'Cual es el presupuesto disponible?',
  'Cuales son las restricciones de participacion?',
];

function getRandomQuestion() {
  return QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];
}

export default function () {
  const scenario = Math.random();

  if (scenario < 0.5) {
    // 50% — RAG queries (most common operation)
    ragQuery();
  } else if (scenario < 0.8) {
    // 30% — health checks
    healthCheck();
  } else {
    // 20% — document status
    getDocument();
  }

  sleep(Math.random() * 2 + 0.5);
}

function ragQuery() {
  const payload = JSON.stringify({
    question: getRandomQuestion(),
    tender_id: TENDER_ID,
    top_k: 5,
  });

  const res = http.post(`${BASE_URL}/api/v1/rag/query`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: 'rag' },
    timeout: '90s',
  });

  const ok = check(res, {
    'rag status 200': (r) => r.status === 200,
    'rag has answer': (r) => {
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
  }
}

function healthCheck() {
  const res = http.get(`${BASE_URL}/api/v1/health`, {
    tags: { endpoint: 'health' },
  });
  check(res, { 'health 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200 ? 1 : 0);
}

function getDocument() {
  const res = http.get(`${BASE_URL}/api/v1/ready`, {
    tags: { endpoint: 'ready' },
  });
  check(res, { 'ready 200': (r) => r.status === 200 });
  errorRate.add(res.status !== 200 ? 1 : 0);
}

export function handleSummary(data) {
  return {
    '/tmp/load_test_summary.json': JSON.stringify(data, null, 2),
    stdout: formatSummary(data),
  };
}

function formatSummary(data) {
  const m = data.metrics;
  const dur = m.http_req_duration;
  return `
╔══════════════════════════════════════════════════════╗
║     PROCUREMENT PLATFORM — LOAD TEST SUMMARY         ║
╠══════════════════════════════════════════════════════╣
║  Total requests:    ${String(m.http_reqs.values.count).padEnd(34)}║
║  Request rate:      ${(m.http_reqs.values.rate || 0).toFixed(2).padEnd(33)}req/s║
║  Error rate:        ${((m.error_rate?.values?.rate || 0)*100).toFixed(2).padEnd(33)}%║
╠══════════════════════════════════════════════════════╣
║  HTTP Duration                                       ║
║    P50:             ${(dur?.values?.['p(50)'] || 0).toFixed(0).padEnd(33)}ms║
║    P90:             ${(dur?.values?.['p(90)'] || 0).toFixed(0).padEnd(33)}ms║
║    P99:             ${(dur?.values?.['p(99)'] || 0).toFixed(0).padEnd(33)}ms║
║    Max:             ${(dur?.values?.max || 0).toFixed(0).padEnd(33)}ms║
╠══════════════════════════════════════════════════════╣
║  RAG Duration                                        ║
║    P50:             ${(m.rag_duration_ms?.values?.['p(50)'] || 0).toFixed(0).padEnd(33)}ms║
║    P90:             ${(m.rag_duration_ms?.values?.['p(90)'] || 0).toFixed(0).padEnd(33)}ms║
║    P99:             ${(m.rag_duration_ms?.values?.['p(99)'] || 0).toFixed(0).padEnd(33)}ms║
╚══════════════════════════════════════════════════════╝
`;
}
