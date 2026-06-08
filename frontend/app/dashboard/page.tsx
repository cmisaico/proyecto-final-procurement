"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw, Server, Database, HardDrive, Brain, CheckCircle, AlertTriangle, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import type { StatusResponse } from "@/lib/types";
import { Card, CardHeader, MetricCard } from "@/components/Card";
import StatusBadge from "@/components/StatusBadge";

const serviceIcons: Record<string, React.ElementType> = {
  postgres: Database,
  qdrant:   HardDrive,
  minio:    HardDrive,
  vllm:     Brain,
};

function ServiceCard({ name, info }: { name: string; info: { status: string; latency_ms: number; detail?: string } }) {
  const Icon = serviceIcons[name] ?? Server;
  const ok = info.status === "ok";
  return (
    <div className="flex items-center justify-between p-4 bg-[#1d2335] rounded-lg">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${ok ? "bg-emerald-500/10" : "bg-red-500/10"}`}>
          <Icon className={`w-4 h-4 ${ok ? "text-emerald-400" : "text-red-400"}`} />
        </div>
        <div>
          <p className="text-white text-sm font-medium capitalize">{name}</p>
          {info.detail && <p className="text-red-400 text-xs mt-0.5 max-w-48 truncate">{info.detail}</p>}
        </div>
      </div>
      <div className="flex items-center gap-4">
        <span className="text-slate-400 text-xs">{info.latency_ms}ms</span>
        <StatusBadge status={info.status} size="sm" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetch = useCallback(async () => {
    try {
      setError(null);
      const res = await api.status();
      setData(res);
      setLastUpdated(new Date());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetch();
    const id = setInterval(fetch, 15000);
    return () => clearInterval(id);
  }, [fetch]);

  const totalServices = data ? Object.keys(data.services).length : 0;
  const okServices = data ? Object.values(data.services).filter((s) => s.status === "ok").length : 0;
  const avgLatency = data
    ? Math.round(Object.values(data.services).reduce((a, s) => a + s.latency_ms, 0) / totalServices)
    : 0;

  return (
    <div className="p-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-2xl font-bold">System Dashboard</h1>
          <p className="text-slate-400 text-sm mt-1">
            {lastUpdated
              ? `Updated ${lastUpdated.toLocaleTimeString()}`
              : "Loading system status…"}
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
          <XCircle className="w-4 h-4 flex-shrink-0" />
          <span>Cannot reach API: {error}</span>
        </div>
      )}

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <MetricCard
          label="Overall Status"
          value={data?.status ?? "—"}
          accent={data?.status === "healthy" ? "text-emerald-400" : data?.status === "degraded" ? "text-yellow-400" : "text-slate-400"}
        />
        <MetricCard
          label="Services Online"
          value={data ? `${okServices}/${totalServices}` : "—"}
          accent={okServices === totalServices && totalServices > 0 ? "text-emerald-400" : "text-yellow-400"}
        />
        <MetricCard
          label="Avg Latency"
          value={data ? `${avgLatency}ms` : "—"}
          sub="across all services"
        />
        <MetricCard
          label="Version"
          value={data?.version ?? "—"}
        />
      </div>

      {/* Services */}
      <Card className="mb-6">
        <CardHeader title="Service Health" subtitle="Real-time dependency status" />
        <div className="p-4 grid gap-3">
          {loading && !data && (
            <div className="text-slate-400 text-sm text-center py-8">Checking services…</div>
          )}
          {data &&
            Object.entries(data.services).map(([name, info]) => (
              <ServiceCard key={name} name={name} info={info} />
            ))}
        </div>
      </Card>

      {/* Config */}
      {data && (
        <Card>
          <CardHeader title="LLM Configuration" />
          <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-4">
            {[
              { label: "LLM Model", value: data.llm_model },
              { label: "Embed Model", value: data.embed_model },
              { label: "Context Top-K", value: data.context_top_k },
              { label: "Max Context Tokens", value: data.max_context_tokens.toLocaleString() },
              { label: "Guardrail Threshold", value: data.guardrail_threshold },
            ].map(({ label, value }) => (
              <div key={label} className="bg-[#1d2335] rounded-lg px-4 py-3">
                <p className="text-slate-400 text-xs mb-1">{label}</p>
                <p className="text-white text-sm font-medium font-mono">{String(value)}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
