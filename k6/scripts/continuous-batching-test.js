/**
 * K6 Continuous Batching Benchmark — vLLM (Fase 4)
 * Tests batch sizes: 1, 4, 8, 16, 32, 64
 * Measures: latency, throughput, GPU utilization, tokens/s
 *
 * Run: k6 run --env VLLM_URL=http://localhost:8000 k6/scripts/continuous-batching-test.js
 */
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Trend, Counter, Rate, Gauge } from 'k6/metrics';

const VLLM_URL  = __ENV.VLLM_URL  || 'http://localhost:8000';
const MODEL     = __ENV.MODEL     || 'qwen2.5-7b';
const PROM_URL  = __ENV.PROM_URL  || 'http://localhost:9090'; // For GPU metrics

// ── Custom Metrics ─────────────────────────────────────────────────────────
const batchLatency  = new Trend('batch_latency_ms',    true);
const tokensPerSec  = new Trend('batch_tokens_per_sec', true);
const throughput    = new Trend('batch_throughput_rps', true);
const gpuUtil       = new Gauge('gpu_utilization_pct');
const batchErrors   = new Counter('batch_errors');
const errorRate     = new Rate('error_rate');

// ── Batch scenarios ────────────────────────────────────────────────────────
// Each batch size runs with enough VUs to sustain that concurrency level.
// We stagger scenarios with 30s gaps for GPU cool-down measurement.
export const options = {
  scenarios: {
    batch_1: {
      executor: 'constant-vus',
      vus: 1,
      duration: '90s',
      startTime: '0s',
      tags: { batch: '1' },
    },
    batch_4: {
      executor: 'constant-vus',
      vus: 4,
      duration: '90s',
      startTime: '2m',
      tags: { batch: '4' },
    },
    batch_8: {
      executor: 'constant-vus',
      vus: 8,
      duration: '90s',
      startTime: '4m',
      tags: { batch: '8' },
    },
    batch_16: {
      executor: 'constant-vus',
      vus: 16,
      duration: '90s',
      startTime: '6m',
      tags: { batch: '16' },
    },
    batch_32: {
      executor: 'constant-vus',
      vus: 32,
      duration: '90s',
      startTime: '8m',
      tags: { batch: '32' },
    },
    batch_64: {
      executor: 'constant-vus',
      vus: 64,
      duration: '90s',
      startTime: '10m',
      tags: { batch: '64' },
    },
  },

  thresholds: {
    // Batch 1 must be fast — single request P99 < 10s
    'batch_latency_ms{batch:1}':  ['p(99)<10000', 'p(50)<5000'],
    // Batch 4 P99 < 15s
    'batch_latency_ms{batch:4}':  ['p(99)<15000'],
    // Batch 8 P99 < 20s
    'batch_latency_ms{batch:8}':  ['p(99)<20000'],
    // Batch 16 P99 < 30s
    'batch_latency_ms{batch:16}': ['p(99)<30000'],
    // Batch 32 P99 < 45s
    'batch_latency_ms{batch:32}': ['p(99)<45000'],
    // Batch 64 P99 < 60s
    'batch_latency_ms{batch:64}': ['p(99)<60000'],
    // Overall error rate < 5%
    error_rate:                   ['rate<0.05'],
  },
};

// ── Test prompts (consistent across all batch sizes for fair comparison) ───
const BENCHMARK_PROMPTS = [
  // Short (≈50 tokens output)
  'Explain what procurement is in one paragraph.',
  // Medium (≈150 tokens output)
  'List the top 5 requirements typically found in a public tender document and explain each briefly.',
  // Long (≈300 tokens output)
  'Write a detailed analysis of the evaluation criteria used in public procurement, including technical, financial, and compliance aspects. Cover at least three specific criteria types.',
];

// Rotate prompts deterministically by VU+iteration for reproducibility
function getPrompt() {
  return BENCHMARK_PROMPTS[(__ITER + __VU) % BENCHMARK_PROMPTS.length];
}

// ── vLLM completions endpoint ──────────────────────────────────────────────
function callVLLM(prompt, maxTokens = 200) {
  const payload = JSON.stringify({
    model: MODEL,
    prompt: prompt,
    max_tokens: maxTokens,
    temperature: 0.1,
    stream: false,
  });

  const start = Date.now();
  const res = http.post(
    `${VLLM_URL}/v1/completions`,
    payload,
    {
      headers: { 'Content-Type': 'application/json' },
      timeout: '90s',
    }
  );
  const elapsed = Date.now() - start;

  const ok = check(res, {
    'vllm status 200': (r) => r.status === 200,
    'vllm has choices': (r) => {
      try {
        const body = JSON.parse(r.body);
        return Array.isArray(body.choices) && body.choices.length > 0;
      } catch { return false; }
    },
  });

  batchLatency.add(elapsed);

  if (ok) {
    errorRate.add(0);
    try {
      const body = JSON.parse(res.body);
      const usage = body.usage || {};
      const completionTokens = usage.completion_tokens || 0;
      const secs = elapsed / 1000;
      if (secs > 0 && completionTokens > 0) {
        tokensPerSec.add(completionTokens / secs);
      }
    } catch { /* ignore parse errors */ }
  } else {
    errorRate.add(1);
    batchErrors.add(1);
  }

  return res;
}

// ── GPU utilization poll (via Prometheus) ─────────────────────────────────
// Called once per VU iteration to sample current GPU utilization
function pollGPUUtilization() {
  const query = encodeURIComponent('DCGM_FI_DEV_GPU_UTIL{gpu="0"}');
  const res = http.get(`${PROM_URL}/api/v1/query?query=${query}`, {
    timeout: '3s',
    tags: { endpoint: 'prometheus' },
  });

  if (res.status === 200) {
    try {
      const data = JSON.parse(res.body);
      const result = data?.data?.result?.[0];
      if (result) {
        const util = parseFloat(result.value[1]);
        if (!isNaN(util)) gpuUtil.add(util);
      }
    } catch { /* ignore */ }
  }
}

// ── Main VU function ───────────────────────────────────────────────────────
export default function () {
  const prompt = getPrompt();

  group('completion', () => {
    callVLLM(prompt, 200);
  });

  // Sample GPU util every ~5 iterations to avoid overloading Prometheus
  if (__ITER % 5 === 0) {
    pollGPUUtilization();
  }

  // No sleep — we want to measure maximum sustained throughput per batch size
}

// ── Summary ────────────────────────────────────────────────────────────────
export function handleSummary(data) {
  const m = data.metrics;

  const batches = [1, 4, 8, 16, 32, 64];

  function batchVal(size, stat) {
    const key = `batch_latency_ms{batch:${size}}`;
    const val = data.metrics[key]?.values?.[stat] || 0;
    return String(val.toFixed(0)).padStart(8);
  }

  function batchTPS(size) {
    const key = `batch_tokens_per_sec{batch:${size}}`;
    const val = data.metrics[key]?.values?.avg || 0;
    return String(val.toFixed(1)).padStart(8);
  }

  function batchReqs(size) {
    // Estimate from http_reqs tagged by scenario
    const key = `http_reqs{batch:${size}}`;
    const count = data.metrics[key]?.values?.count || 0;
    const rate  = data.metrics[key]?.values?.rate  || 0;
    return { count: String(count).padStart(6), rate: String(rate.toFixed(2)).padStart(8) };
  }

  const overall_tps = m.batch_tokens_per_sec?.values || {};
  const overall_lat = m.batch_latency_ms?.values || {};
  const gpu_max     = m.gpu_utilization_pct?.values?.max || 0;
  const err         = m.error_rate?.values?.rate || 0;

  let rows = '';
  for (const b of batches) {
    const reqs = batchReqs(b);
    rows += `║  ${String(b).padEnd(10)} │${batchVal(b,'med')} ms │${batchVal(b,'p(90)')} ms │${batchVal(b,'p(99)')} ms │${batchTPS(b)} t/s │${reqs.rate} req/s ║\n`;
  }

  const report = `
╔════════════════════════════════════════════════════════════════════════════════╗
║       CONTINUOUS BATCHING BENCHMARK — vLLM (Qwen2.5-7B) on RTX 5080          ║
╠════════════════════════════════════════════════════════════════════════════════╣
║  Batch Size  │  P50 (ms) │  P90 (ms) │  P99 (ms) │  Tokens/s │  Req/s      ║
╠════════════════════════════════════════════════════════════════════════════════╣
${rows}╠════════════════════════════════════════════════════════════════════════════════╣
║  OVERALL SUMMARY                                                               ║
║    P50 latency:    ${String((overall_lat.med||0).toFixed(0)).padEnd(8)} ms                                               ║
║    P99 latency:    ${String((overall_lat['p(99)']||0).toFixed(0)).padEnd(8)} ms                                               ║
║    Avg tokens/s:   ${String((overall_tps.avg||0).toFixed(1)).padEnd(8)} t/s                                               ║
║    Max tokens/s:   ${String((overall_tps.max||0).toFixed(1)).padEnd(8)} t/s                                               ║
║    Max GPU util:   ${String(gpu_max.toFixed(1)).padEnd(8)} %                                                ║
║    Error rate:     ${((err)*100).toFixed(2).padEnd(8)} %                                                ║
╠════════════════════════════════════════════════════════════════════════════════╣
║  EFFICIENCY NOTES                                                              ║
║    • vLLM continuous batching merges concurrent requests automatically         ║
║    • Higher batch sizes → better GPU utilization but higher tail latency       ║
║    • RTX 5080 16GB VRAM target: >80% GPU util at batch ≥ 16                   ║
║    • Optimal operating point: batch 8-16 for latency-throughput balance        ║
╚════════════════════════════════════════════════════════════════════════════════╝
`;

  return {
    stdout: report,
    'k6/results/continuous_batching.json': JSON.stringify(data, null, 2),
  };
}
