"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { RefreshCw, TrendingUp, AlertCircle, WifiOff } from "lucide-react";
import { api } from "@/lib/api";
import type { CostReport } from "@/lib/types";
import { Card, CardHeader, MetricCard } from "@/components/Card";

function Bar({ label, value, max, color, current }: { label: string; value: number; max: number; color: string; current?: boolean }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-slate-400 text-xs flex items-center gap-2">
          {label}
          {current && (
            <span className="px-1.5 py-0.5 bg-emerald-500/20 text-emerald-400 text-[10px] rounded font-mono">
              current
            </span>
          )}
        </span>
        <span className="text-white text-xs font-mono">${value.toFixed(4)}</span>
      </div>
      <div className="h-2 bg-[#1d2335] rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.max(pct, 2)}%` }} />
      </div>
    </div>
  );
}

export default function CostPage() {
  const [data, setData] = useState<CostReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  // Keeps the last response where Prometheus returned real data
  const lastValid = useRef<CostReport | null>(null);

  const fetch = useCallback(async () => {
    try {
      setError(null);
      const res = await api.getCostAnalysis();
      if (res.prometheus_available) {
        lastValid.current = res;
        setData(res);
        setStale(false);
      } else if (lastValid.current) {
        // Prometheus unreachable — show last known values instead of zeros
        setData(lastValid.current);
        setStale(true);
      } else {
        setData(res);
        setStale(false);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
    const id = setInterval(fetch, 30000);
    return () => clearInterval(id);
  }, [fetch]);

  const breakdown = data?.breakdown as Record<string, Record<string, unknown>> | undefined;

  const t4Spot     = data?.cost_vllm_per_1k_requests_usd ?? 0;
  const t4OnDemand = data?.cost_aks_cpu_per_1k_requests_usd ?? 0;
  const v100       = data?.cost_aks_gpu_per_1k_requests_usd ?? 0;
  const maxCost    = Math.max(t4Spot, t4OnDemand, v100, 0.01);

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-2xl font-bold">Cost Analysis</h1>
          <p className="text-slate-400 text-sm mt-1">
            LLMOps — AKS T4 Spot · vLLM · Qwen2.5-7B-AWQ
          </p>
        </div>
        <button
          onClick={fetch}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-2 bg-[#1d2335] hover:bg-[#2a3347] border border-[#2a3347] rounded-lg text-slate-300 text-sm transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 mb-6 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {stale && !error && (
        <div className="flex items-center gap-2 mb-6 px-4 py-3 bg-yellow-500/10 border border-yellow-500/20 rounded-lg text-yellow-400 text-sm">
          <WifiOff className="w-4 h-4 flex-shrink-0" />
          Prometheus no disponible — mostrando último valor conocido
        </div>
      )}

      {/* Token metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="Total Tokens"
          value={data ? data.total_tokens.toLocaleString() : "—"}
          sub="since startup"
        />
        <MetricCard
          label="Input Tokens"
          value={data ? data.input_tokens.toLocaleString() : "—"}
          accent="text-blue-400"
        />
        <MetricCard
          label="Output Tokens"
          value={data ? data.output_tokens.toLocaleString() : "—"}
          accent="text-indigo-400"
        />
        <MetricCard
          label="Tokens / Second"
          value={data ? data.tokens_per_second_current : "—"}
          sub="vLLM throughput"
          accent="text-emerald-400"
        />
      </div>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <MetricCard
          label="Avg Tokens / Request"
          value={data ? data.avg_tokens_per_request.toLocaleString() : "—"}
          sub="across all workflows"
        />
        <MetricCard
          label="Current Node"
          value="T4 Spot"
          sub="Standard_NC4as_T4_v3 · $0.158/hr"
          accent="text-emerald-400"
        />
      </div>

      {/* Cost comparison */}
      {data && (
        <Card className="mb-6">
          <CardHeader
            title="Deployment Cost Comparison"
            subtitle="Cost per 1,000 requests across AKS options"
          />
          <div className="p-5 space-y-4">
            <Bar
              label="AKS T4 Spot — NC4as_T4_v3 · $0.158/hr"
              value={t4Spot}
              max={maxCost}
              color="bg-emerald-500"
              current
            />
            <Bar
              label="AKS T4 On-demand — NC4as_T4_v3 · $0.526/hr"
              value={t4OnDemand}
              max={maxCost}
              color="bg-yellow-500"
            />
            <Bar
              label="AKS V100 On-demand — NC6s_v3 · $3.06/hr"
              value={v100}
              max={maxCost}
              color="bg-orange-500"
            />
            <div className="pt-2 border-t border-[#2a3347]">
              <div className="flex justify-between text-xs text-slate-500">
                <span>$0</span>
                <span>${maxCost.toFixed(4)} / 1k requests</span>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Breakdown */}
      {breakdown && (
        <Card className="mb-6">
          <CardHeader title="Infrastructure Breakdown" />
          <div className="p-4 grid md:grid-cols-3 gap-4">
            {Object.entries(breakdown).map(([key, val]) => (
              <div key={key} className="bg-[#1d2335] rounded-xl p-4 space-y-2">
                <p className="text-indigo-300 text-xs font-mono uppercase tracking-wider">
                  {key.replace(/_/g, " ")}
                </p>
                {Object.entries(val).map(([k, v]) => (
                  <div key={k} className="flex items-start justify-between gap-2">
                    <span className="text-slate-500 text-xs capitalize">{k.replace(/_/g, " ")}</span>
                    <span className="text-white text-xs font-mono text-right">{String(v)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Recommendations */}
      {data && data.recommendations.length > 0 && (
        <Card>
          <CardHeader title="Recommendations" />
          <div className="p-4 space-y-2">
            {data.recommendations.map((r, i) => (
              <div key={i} className="flex items-start gap-3 bg-[#1d2335] rounded-lg px-4 py-3">
                <TrendingUp className="w-4 h-4 text-indigo-400 mt-0.5 flex-shrink-0" />
                <p className="text-slate-300 text-sm">{r}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}