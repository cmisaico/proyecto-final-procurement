"use client";

import { useState, useEffect, useRef } from "react";
import {
  Play, Scale, FileEdit, ShieldCheck, FileOutput,
  CheckCircle, Clock, AlertCircle, Loader2, ChevronDown, ChevronUp
} from "lucide-react";
import { api } from "@/lib/api";
import type { FullAnalysisResponse } from "@/lib/types";
import { Card, CardHeader } from "@/components/Card";
import StatusBadge from "@/components/StatusBadge";

const STEPS = [
  { key: "legal_analysis", label: "Legal Analysis", icon: Scale, desc: "Extracts requirements, risks, and legal obligations" },
  { key: "proposal_generation", label: "Proposal Generation", icon: FileEdit, desc: "Drafts a compliance-focused proposal" },
  { key: "compliance_audit", label: "Compliance Audit", icon: ShieldCheck, desc: "Validates proposal against requirements" },
  { key: "report_generation", label: "Report Generation", icon: FileOutput, desc: "Produces final audit report" },
];

function JsonBlock({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-[#2a3347] rounded-lg overflow-hidden mt-2">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-[#1d2335] text-slate-400 text-xs hover:bg-[#252f47] transition-colors"
      >
        <span>View raw output</span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <pre className="p-3 bg-[#0f1117] text-slate-300 text-xs overflow-x-auto max-h-64">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function WorkflowPage() {
  const [tenderId, setTenderId] = useState("");
  const [result, setResult] = useState<FullAnalysisResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runAnalysis() {
    if (!tenderId.trim() || running) return;
    setError(null);
    setResult(null);
    setRunning(true);
    try {
      const res = await api.runFullAnalysis(tenderId.trim());
      setResult(res);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const final = result?.final_report as Record<string, unknown> | null | undefined;

  return (
    <div className="p-6 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Multi-Agent Workflow</h1>
        <p className="text-slate-400 text-sm mt-1">
          Runs Legal Analysis → Proposal Generation → Compliance Audit → Report
        </p>
      </div>

      {/* Pipeline visualization */}
      <Card className="mb-6">
        <CardHeader title="Pipeline" />
        <div className="p-4 flex items-center gap-2 flex-wrap">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            const completed = result?.steps_completed.includes(step.key);
            const active = running && !result;
            return (
              <div key={step.key} className="flex items-center gap-2">
                <div className={`flex flex-col items-center p-3 rounded-xl border transition-colors min-w-28 ${
                  completed
                    ? "border-emerald-500/40 bg-emerald-500/5"
                    : active
                    ? "border-indigo-500/40 bg-indigo-500/5"
                    : "border-[#2a3347] bg-[#1d2335]"
                }`}>
                  <Icon className={`w-5 h-5 mb-1 ${completed ? "text-emerald-400" : active ? "text-indigo-400 animate-pulse" : "text-slate-500"}`} />
                  <p className={`text-xs font-medium text-center ${completed ? "text-emerald-400" : active ? "text-indigo-300" : "text-slate-400"}`}>
                    {step.label}
                  </p>
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`w-6 h-0.5 flex-shrink-0 ${completed ? "bg-emerald-500/40" : "bg-[#2a3347]"}`} />
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Run form */}
      <Card className="mb-6">
        <CardHeader title="Run Analysis" subtitle="Processes all documents for the given tender" />
        <div className="p-5">
          <div className="flex gap-3">
            <input
              value={tenderId}
              onChange={(e) => setTenderId(e.target.value)}
              placeholder="Tender ID (e.g. TENDER-2024-001)"
              onKeyDown={(e) => e.key === "Enter" && runAnalysis()}
              className="flex-1 bg-[#0f1117] border border-[#2a3347] rounded-lg px-3 py-2.5 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <button
              onClick={runAnalysis}
              disabled={!tenderId.trim() || running}
              className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {running ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Running…</>
              ) : (
                <><Play className="w-4 h-4" /> Run</>
              )}
            </button>
          </div>
          {error && (
            <div className="flex items-center gap-2 mt-3 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}
        </div>
      </Card>

      {/* Results */}
      {result && (
        <div className="space-y-4">
          {/* Summary */}
          <Card>
            <CardHeader
              title="Workflow Result"
              subtitle={`Workflow ID: ${result.workflow_id.slice(0, 8)}…`}
              action={<StatusBadge status={result.status} />}
            />
            <div className="p-4 grid grid-cols-2 gap-3">
              <div className="bg-[#1d2335] rounded-lg p-3">
                <p className="text-slate-400 text-xs mb-1">Tender</p>
                <p className="text-white text-sm font-mono">{result.tender_id}</p>
              </div>
              <div className="bg-[#1d2335] rounded-lg p-3">
                <p className="text-slate-400 text-xs mb-1">Steps Completed</p>
                <p className="text-emerald-400 text-sm font-medium">{result.steps_completed.length} / {STEPS.length}</p>
              </div>
              {result.errors.length > 0 && (
                <div className="col-span-2 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
                  <p className="text-red-400 text-xs font-medium mb-1">Errors</p>
                  {result.errors.map((e, i) => <p key={i} className="text-red-400 text-xs">{e}</p>)}
                </div>
              )}
            </div>
          </Card>

          {/* Final report */}
          {final && (
            <Card>
              <CardHeader title="Final Report" />
              <div className="p-4 space-y-3">
                {(final.summary as string) && (
                  <div className="bg-[#1d2335] rounded-lg p-4">
                    <p className="text-slate-400 text-xs mb-2 uppercase tracking-wider">Summary</p>
                    <p className="text-slate-200 text-sm leading-relaxed">{final.summary as string}</p>
                  </div>
                )}
                {(final.compliance_score as number) !== undefined && (
                  <div className="flex items-center gap-4">
                    <div className="bg-[#1d2335] rounded-lg p-4 flex-1 text-center">
                      <p className="text-slate-400 text-xs mb-1">Compliance Score</p>
                      <p className={`text-3xl font-bold ${
                        (final.compliance_score as number) >= 0.8 ? "text-emerald-400" :
                        (final.compliance_score as number) >= 0.6 ? "text-yellow-400" : "text-red-400"
                      }`}>
                        {Math.round((final.compliance_score as number) * 100)}%
                      </p>
                    </div>
                    {typeof final.risk_level === "string" && (
                      <div className="bg-[#1d2335] rounded-lg p-4 flex-1 text-center">
                        <p className="text-slate-400 text-xs mb-1">Risk Level</p>
                        <StatusBadge status={final.risk_level} />
                      </div>
                    )}
                  </div>
                )}
                {Array.isArray(final.recommendations) && final.recommendations.length > 0 && (
                  <div className="bg-[#1d2335] rounded-lg p-4">
                    <p className="text-slate-400 text-xs mb-2 uppercase tracking-wider">Recommendations</p>
                    <ul className="space-y-1.5">
                      {(final.recommendations as string[]).map((r, i) => (
                        <li key={i} className="flex items-start gap-2 text-slate-300 text-sm">
                          <CheckCircle className="w-3.5 h-3.5 text-indigo-400 mt-0.5 flex-shrink-0" />
                          {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <JsonBlock data={final} />
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
