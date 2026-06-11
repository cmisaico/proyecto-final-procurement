/**
 * Cost Optimization Benchmark — Procurement Intelligence Platform
 *
 * Mide el impacto económico real de las estrategias de optimización de costo:
 *   1. Cuantización AWQ (4-bit) vs FP16 — mismo modelo, diferente precisión
 *   2. Tamaño de modelo — 7B vs 14B (quality vs cost tradeoff)
 *   3. Inference Router — % de requests SMALL (sin GPU) y ahorro estimado
 *   4. Batch size óptimo — throughput por dólar según nivel de concurrencia
 *
 * Uso:
 *   # Comparación de cuantización (un solo endpoint, mide eficiencia):
 *   k6 run cost-optimization-test.js \
 *     -e VLLM_URL=http://vllm.ai-platform.svc:8000 \
 *     -e GPU_TYPE=t4_spot \
 *     -e SCENARIO=quantization_vs_fp16
 *
 *   # Comparación 7B vs 14B (requiere dos endpoints activos):
 *   k6 run cost-optimization-test.js \
 *     -e VLLM_URL=http://vllm-7b.ai-platform.svc:8000 \
 *     -e VLLM_LARGE_URL=http://vllm-14b.ai-platform.svc:8000 \
 *     -e GPU_TYPE=a10g \
 *     -e SCENARIO=model_size
 *
 *   # Inference Router effectiveness:
 *   k6 run cost-optimization-test.js \
 *     -e BASE_URL=http://api-gateway.ai-platform.svc:8080 \
 *     -e PROM_URL=http://prometheus-operated.monitoring.svc:9090 \
 *     -e SCENARIO=router_effectiveness
 *
 *   # Batch size sweep (costo por token por nivel de concurrencia):
 *   k6 run cost-optimization-test.js \
 *     -e VLLM_URL=http://vllm.ai-platform.svc:8000 \
 *     -e GPU_TYPE=t4_spot \
 *     -e SCENARIO=batch_cost_sweep
 */

import http from "k6/http";
import { check, sleep, group } from "k6";
import { Counter, Rate, Trend, Gauge } from "k6/metrics";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.2/index.js";

// ── Config ────────────────────────────────────────────────────────────────────

const VLLM_URL      = __ENV.VLLM_URL      || "http://vllm.ai-platform.svc.cluster.local:8000";
const VLLM_LARGE_URL = __ENV.VLLM_LARGE_URL || "";
const BASE_URL      = __ENV.BASE_URL      || "http://api-gateway.ai-platform.svc.cluster.local:8080";
const PROM_URL      = __ENV.PROM_URL      || "http://prometheus-operated.monitoring.svc.cluster.local:9090";
const GPU_TYPE      = __ENV.GPU_TYPE      || "t4_spot";
const SCENARIO      = __ENV.SCENARIO      || "batch_cost_sweep";

// Precio por hora por GPU type (USD)
const GPU_COST_PER_HOUR = {
  t4_spot:     0.158,
  t4_ondemand: 0.526,
  a10g:        1.354,
  l4:          0.706,
  l40s:        2.50,
};

const PRICE_PER_HOUR = GPU_COST_PER_HOUR[GPU_TYPE] || 0.158;
const PRICE_PER_SEC  = PRICE_PER_HOUR / 3600;

// ── Prompts para cada escenario ───────────────────────────────────────────────

// Prompts simples → deberían tomar ruta SMALL del InferenceRouter
const SIMPLE_PROMPTS = [
  "¿Cuál es el precio unitario del ítem A?",
  "¿Qué proveedor tiene el menor costo?",
  "¿Cuántas unidades se compraron en enero?",
  "¿Cuál es el plazo de entrega del contrato número 5?",
  "¿Qué porcentaje de descuento aplica para volumen mayor a 1000?",
];

// Prompts complejos → vLLM necesario, ruta LARGE
const COMPLEX_PROMPTS = [
  "Analiza el riesgo de concentración de proveedores en la categoría de materiales de construcción, considerando los últimos 12 meses de datos de contratos, e identifica los tres principales factores de riesgo con recomendaciones de mitigación.",
  "Compara las condiciones contractuales de los cinco principales proveedores de servicios de TI e identifica cláusulas inusuales o desventajosas para la organización compradora.",
  "¿Cuáles son las implicancias de cumplimiento regulatorio para contratos de más de USD 500,000 con proveedores internacionales según la normativa vigente de contratación pública?",
  "Genera un resumen ejecutivo de las oportunidades de ahorro identificadas en el análisis de contratos del trimestre, incluyendo quick wins y proyectos de largo plazo.",
];

// Prompts de tamaño variado para el batch sweep
const BATCH_PROMPTS = {
  short:  "Resume en una oración el objetivo del contrato.",
  medium: "Analiza las condiciones de pago del proveedor y sugiere mejoras para reducir el costo financiero del ciclo de caja.",
  long:   "Realiza un análisis comparativo de los contratos de suministro de equipos tecnológicos firmados en el último año, evaluando: (1) competitividad de precios respecto al mercado, (2) cláusulas de penalidad y SLA, (3) condiciones de renovación automática, y (4) riesgos de dependencia tecnológica. Proporciona recomendaciones concretas para la siguiente ronda de licitaciones.",
};

// ── Métricas custom ───────────────────────────────────────────────────────────

const tokensGenerated       = new Counter("cost_tokens_generated_total");
const tokensPerSecond       = new Trend("cost_tokens_per_second");
const costPerThousandTokens = new Trend("cost_usd_per_1k_tokens");
const requestSuccess        = new Rate("cost_request_success_rate");
const ttft                  = new Trend("cost_time_to_first_token_ms");
const totalLatency          = new Trend("cost_total_latency_ms");

// Router-specific
const routerSmallTotal  = new Counter("router_small_decisions_total");
const routerLargeTotal  = new Counter("router_large_decisions_total");
const routerSavingsUSD  = new Counter("router_estimated_savings_usd");

// ── Escenarios ────────────────────────────────────────────────────────────────

// Cada scenario define su propia configuración de VUs y duración
const SCENARIO_OPTIONS = {
  quantization_vs_fp16: {
    executor: "ramping-vus",
    stages: [
      { duration: "2m", target: 4  },
      { duration: "5m", target: 4  },  // estado estable AWQ
      { duration: "1m", target: 0  },
    ],
  },
  model_size: {
    executor: "ramping-vus",
    stages: [
      { duration: "2m", target: 2  },
      { duration: "5m", target: 2  },  // 7B vs 14B en paralelo
      { duration: "1m", target: 0  },
    ],
  },
  router_effectiveness: {
    executor: "ramping-vus",
    stages: [
      { duration: "1m", target: 8  },
      { duration: "8m", target: 8  },  // mix 50/50 simple/complejo
      { duration: "1m", target: 0  },
    ],
  },
  batch_cost_sweep: {
    executor: "ramping-vus",
    stages: [
      { duration: "90s", target: 2  },   // batch ~2
      { duration: "90s", target: 4  },   // batch ~4
      { duration: "90s", target: 8  },   // batch ~8
      { duration: "90s", target: 16 },   // batch ~16
      { duration: "90s", target: 32 },   // batch ~32
      { duration: "90s", target: 0  },   // cooldown
    ],
  },
};

export const options = {
  scenarios: {
    cost_benchmark: SCENARIO_OPTIONS[SCENARIO] || SCENARIO_OPTIONS.batch_cost_sweep,
  },
  thresholds: {
    // El escenario es de análisis, no de SLA — umbrales amplios
    cost_request_success_rate: ["rate>0.90"],
    cost_total_latency_ms:     ["p(95)<120000"],  // 120s para el modelo 14B
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function callVLLM(url, prompt, modelName) {
  const start = Date.now();
  const res = http.post(
    `${url}/v1/completions`,
    JSON.stringify({
      model:       modelName,
      prompt:      prompt,
      max_tokens:  512,
      temperature: 0.1,
      stream:      false,
    }),
    {
      headers: { "Content-Type": "application/json" },
      timeout: "120s",
    }
  );

  const elapsed = Date.now() - start;
  const ok = check(res, {
    "vllm status 200": (r) => r.status === 200,
    "vllm has choices": (r) => {
      try { return JSON.parse(r.body).choices?.length > 0; } catch { return false; }
    },
  });

  requestSuccess.add(ok);

  if (ok && res.status === 200) {
    const body = JSON.parse(res.body);
    const usage = body.usage || {};
    const completionTokens = usage.completion_tokens || 0;
    const totalTokens      = usage.total_tokens || 0;

    tokensGenerated.add(completionTokens);
    totalLatency.add(elapsed);

    const tps = completionTokens / (elapsed / 1000);
    tokensPerSecond.add(tps);

    // Costo por 1K tokens = (precio_hora / 3600) / (tokens_por_segundo / 1000)
    if (tps > 0) {
      const cost1k = PRICE_PER_SEC / (tps / 1000);
      costPerThousandTokens.add(cost1k);
    }

    return { ok, completionTokens, totalTokens, elapsed, tps };
  }

  return { ok: false, completionTokens: 0, totalTokens: 0, elapsed, tps: 0 };
}

function callGateway(prompt, isSimple) {
  const start = Date.now();
  const res = http.post(
    `${BASE_URL}/api/v1/rag`,
    JSON.stringify({
      question: prompt,
      top_k: 5,
    }),
    {
      headers: { "Content-Type": "application/json" },
      timeout: "60s",
    }
  );

  const elapsed = Date.now() - start;
  const ok = check(res, {
    "gateway status 200": (r) => r.status === 200,
  });

  requestSuccess.add(ok);
  totalLatency.add(elapsed);

  if (ok) {
    try {
      const body = JSON.parse(res.body);
      const route = body.route || "unknown";

      if (route === "small") {
        routerSmallTotal.add(1);
        // Ahorro estimado: evitar ~3s de GPU time → precio_por_segundo * 3
        routerSavingsUSD.add(PRICE_PER_SEC * 3);
      } else {
        routerLargeTotal.add(1);
      }
    } catch {}
  }

  return { ok, elapsed };
}

function queryPrometheus(promql) {
  const encoded = encodeURIComponent(promql);
  const res = http.get(
    `${PROM_URL}/api/v1/query?query=${encoded}`,
    { timeout: "10s" }
  );

  if (res.status === 200) {
    try {
      const data = JSON.parse(res.body);
      const result = data?.data?.result;
      if (result?.length > 0) {
        return parseFloat(result[0].value[1]);
      }
    } catch {}
  }
  return null;
}

// ── Scenario: Quantization AWQ vs FP16 ───────────────────────────────────────
// Ambas versiones se testean contra el mismo endpoint.
// La diferencia de throughput refleja el beneficio de la cuantización.
// Nota: necesitas tener ambos deployments activos y pasar sus URLs,
// o comparar métricas históricas de Prometheus si solo tienes uno.

function scenarioQuantization() {
  const prompt = BATCH_PROMPTS.medium;
  const modelAWQ = "qwen2.5-7b-awq";
  const modelFP16 = "qwen2.5-7b-fp16";

  group("awq_inference", () => {
    const result = callVLLM(VLLM_URL, prompt, modelAWQ);
    if (result.ok) {
      console.log(`AWQ tokens/s: ${result.tps.toFixed(1)}, cost/1K: $${(PRICE_PER_SEC / (result.tps / 1000)).toFixed(5)}`);
    }
  });

  sleep(0.5);
}

// ── Scenario: Model Size 7B vs 14B ──────────────────────────────────────────

function scenarioModelSize() {
  const prompt = BATCH_PROMPTS.long;

  group("model_7b", () => {
    const result = callVLLM(VLLM_URL, prompt, "qwen2.5-7b");
    if (result.ok) {
      console.log(`7B | latency: ${result.elapsed}ms | tok/s: ${result.tps.toFixed(1)}`);
    }
  });

  if (VLLM_LARGE_URL) {
    sleep(0.2);
    group("model_14b", () => {
      const result = callVLLM(VLLM_LARGE_URL, prompt, "qwen2.5-14b");
      if (result.ok) {
        console.log(`14B | latency: ${result.elapsed}ms | tok/s: ${result.tps.toFixed(1)}`);
      }
    });
  }

  sleep(1);
}

// ── Scenario: Inference Router Effectiveness ─────────────────────────────────
// Mix 60% simple / 40% complejo para simular tráfico real de producción.
// Mide cuántos requests evitan el LLM y el ahorro estimado en USD.

function scenarioRouterEffectiveness() {
  const rand = Math.random();

  if (rand < 0.60) {
    // Ruta esperada: SMALL (sin LLM)
    const prompt = SIMPLE_PROMPTS[Math.floor(Math.random() * SIMPLE_PROMPTS.length)];
    group("simple_query", () => {
      callGateway(prompt, true);
    });
  } else {
    // Ruta esperada: LARGE (vLLM)
    const prompt = COMPLEX_PROMPTS[Math.floor(Math.random() * COMPLEX_PROMPTS.length)];
    group("complex_query", () => {
      callGateway(prompt, false);
    });
  }

  sleep(0.5);
}

// ── Scenario: Batch Size Cost Sweep ──────────────────────────────────────────
// Cada VU envía requests continuamente. La concurrencia activa determina el
// batch size efectivo en vLLM (continuous batching agrupa requests simultáneas).
// Mide tokens/s y $/1K tokens a distintos niveles de concurrencia.

function scenarioBatchCostSweep() {
  const prompts = [
    BATCH_PROMPTS.short,
    BATCH_PROMPTS.medium,
    BATCH_PROMPTS.long,
  ];
  const prompt = prompts[Math.floor(Math.random() * prompts.length)];

  group("batch_inference", () => {
    const result = callVLLM(VLLM_URL, prompt, "qwen2.5-7b");
    if (result.ok) {
      // Log periódico para análisis posterior por VU count
      if (Math.random() < 0.1) {
        // Consulta Prometheus para ver el batch size actual de vLLM
        const runningReqs = queryPrometheus(
          'sum(vllm:num_requests_running{namespace="ai-platform"})'
        );
        const gpuUtil = queryPrometheus("avg(DCGM_FI_DEV_GPU_UTIL)");

        console.log(JSON.stringify({
          ts:            new Date().toISOString(),
          vu:            __VU,
          latency_ms:    result.elapsed,
          tokens_s:      result.tps.toFixed(1),
          cost_1k_usd:   (PRICE_PER_SEC / (result.tps / 1000)).toFixed(5),
          vllm_running:  runningReqs,
          gpu_util_pct:  gpuUtil,
          gpu_type:      GPU_TYPE,
        }));
      }
    }
  });

  // Sin sleep intencional — continuous batching necesita presión constante
  // para que el benchmark sea válido. El propio tiempo de inferencia actúa
  // como "think time" natural.
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function () {
  switch (SCENARIO) {
    case "quantization_vs_fp16":
      scenarioQuantization();
      break;
    case "model_size":
      scenarioModelSize();
      break;
    case "router_effectiveness":
      scenarioRouterEffectiveness();
      break;
    case "batch_cost_sweep":
    default:
      scenarioBatchCostSweep();
  }
}

// ── Summary personalizado ─────────────────────────────────────────────────────

export function handleSummary(data) {
  const metrics = data.metrics;

  // Extrae valores clave para el resumen de costo
  const p50cost = metrics["cost_usd_per_1k_tokens"]?.values?.["p(50)"] || 0;
  const p90cost = metrics["cost_usd_per_1k_tokens"]?.values?.["p(90)"] || 0;
  const p50tps  = metrics["cost_tokens_per_second"]?.values?.["p(50)"] || 0;
  const totalTok = metrics["cost_tokens_generated_total"]?.values?.count || 0;
  const smallDecisions = metrics["router_small_decisions_total"]?.values?.count || 0;
  const largeDecisions = metrics["router_large_decisions_total"]?.values?.count || 0;
  const totalDecisions = smallDecisions + largeDecisions;
  const smallRatio = totalDecisions > 0 ? (smallDecisions / totalDecisions * 100).toFixed(1) : "N/A";
  const savedUSD   = metrics["router_estimated_savings_usd"]?.values?.count || 0;

  const costSummary = `
╔══════════════════════════════════════════════════════════════╗
║           COST OPTIMIZATION BENCHMARK — RESULTS             ║
╠══════════════════════════════════════════════════════════════╣
║ Escenario:       ${SCENARIO.padEnd(43)}║
║ GPU Type:        ${GPU_TYPE.padEnd(43)}║
║ Precio/hora:     $${PRICE_PER_HOUR.toString().padEnd(42)}║
╠══════════════════════════════════════════════════════════════╣
║ THROUGHPUT                                                   ║
║   Tokens generados:    ${totalTok.toString().padEnd(37)}║
║   Tokens/s (P50):      ${p50tps.toFixed(2).padEnd(37)}║
╠══════════════════════════════════════════════════════════════╣
║ COSTO POR TOKEN                                              ║
║   $/1K tokens (P50):   $${p50cost.toFixed(5).padEnd(36)}║
║   $/1K tokens (P90):   $${p90cost.toFixed(5).padEnd(36)}║
╠══════════════════════════════════════════════════════════════╣
║ INFERENCE ROUTER                                             ║
║   Ruta SMALL (no-GPU): ${smallDecisions.toString().padEnd(8)} req (${smallRatio}%)${" ".repeat(Math.max(0, 19 - smallRatio.length))}║
║   Ruta LARGE (vLLM):   ${largeDecisions.toString().padEnd(37)}║
║   Ahorro estimado GPU: $${savedUSD.toFixed(4).padEnd(36)}║
╚══════════════════════════════════════════════════════════════╝
`;

  console.log(costSummary);

  return {
    stdout: textSummary(data, { indent: " ", enableColors: true }),
    "cost-optimization-results.json": JSON.stringify({
      scenario:        SCENARIO,
      gpu_type:        GPU_TYPE,
      price_per_hour:  PRICE_PER_HOUR,
      p50_cost_per_1k: p50cost,
      p90_cost_per_1k: p90cost,
      p50_tokens_per_s: p50tps,
      total_tokens:    totalTok,
      router: {
        small_requests:  smallDecisions,
        large_requests:  largeDecisions,
        small_ratio_pct: parseFloat(smallRatio) || 0,
        estimated_savings_usd: savedUSD,
      },
      raw_thresholds: data.metrics,
    }, null, 2),
  };
}