"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, CheckCircle, AlertTriangle, XCircle,
  Scale, FileEdit, ShieldCheck, FileOutput, ChevronDown, ChevronUp, CalendarDays
} from "lucide-react";
import { api } from "@/lib/api";
import type { ComplianceReportResponse, AuditReportResponse, DashboardResponse } from "@/lib/types";
import { Card, CardHeader } from "@/components/Card";
import StatusBadge from "@/components/StatusBadge";

function ScoreRing({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = pct >= 80 ? "#34d399" : pct >= 60 ? "#fbbf24" : "#f87171";
  const r = 42;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <div className="flex flex-col items-center gap-1">
      <svg width="100" height="100" viewBox="0 0 100 100" className="-rotate-90">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#2a3347" strokeWidth="8" />
        <circle
          cx="50" cy="50" r={r} fill="none"
          stroke={color} strokeWidth="8"
          strokeDasharray={`${dash} ${circ}`}
          strokeLinecap="round"
        />
      </svg>
      <div className="text-center -mt-[72px] mb-[52px]">
        <p className="text-2xl font-bold" style={{ color }}>{pct}%</p>
        <p className="text-slate-400 text-xs">Compliance</p>
      </div>
    </div>
  );
}

function Section({ title, icon: Icon, data }: { title: string; icon: React.ElementType; data: unknown }) {
  const [open, setOpen] = useState(false);
  if (!data) return null;
  const obj = data as Record<string, unknown>;
  return (
    <div className="border border-[#2a3347] rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-[#1d2335] hover:bg-[#252f47] transition-colors"
      >
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-indigo-400" />
          <span className="text-white text-sm font-medium">{title}</span>
        </div>
        {open ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
      </button>
      {open && (
        <div className="p-4 bg-[#161b27] space-y-3">
          {typeof obj.summary === "string" && <p className="text-slate-300 text-sm leading-relaxed">{obj.summary}</p>}
          {Array.isArray(obj.requirements) && obj.requirements.length > 0 && (
            <div>
              <p className="text-slate-500 text-xs uppercase tracking-wider mb-2">Requirements</p>
              <ul className="space-y-1">
                {(obj.requirements as string[]).map((r, i) => (
                  <li key={i} className="flex items-start gap-2 text-slate-300 text-sm">
                    <CheckCircle className="w-3.5 h-3.5 text-indigo-400 mt-0.5 flex-shrink-0" />
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <details className="text-xs">
            <summary className="text-slate-500 cursor-pointer">Raw JSON</summary>
            <pre className="mt-2 p-2 bg-[#0f1117] rounded text-slate-400 overflow-x-auto max-h-48">
              {JSON.stringify(obj, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default function ReportPage() {
  const { tenderId } = useParams<{ tenderId: string }>();
  const decoded = decodeURIComponent(tenderId);

  const [compliance, setCompliance] = useState<ComplianceReportResponse | null>(null);
  const [audit, setAudit] = useState<AuditReportResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [c, d] = await Promise.all([
          api.getCompliance(decoded),
          api.getDashboard(decoded),
        ]);
        setCompliance(c);
        setDashboard(d);
        if (c.workflow_id) {
          const a = await api.getReport(c.workflow_id);
          setAudit(a);
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [decoded]);

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/reports" className="p-2 hover:bg-[#1d2335] rounded-lg transition-colors">
          <ArrowLeft className="w-4 h-4 text-slate-400" />
        </Link>
        <div>
          <h1 className="text-white text-2xl font-bold">{decoded}</h1>
          <p className="text-slate-400 text-sm mt-0.5">Compliance & Audit Report</p>
        </div>
      </div>

      {loading && (
        <div className="text-slate-400 text-sm text-center py-20">Loading report…</div>
      )}

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          <XCircle className="w-4 h-4" />
          {error}
        </div>
      )}

      {!loading && !error && compliance && (
        <div className="space-y-5">
          {/* Score + summary */}
          <Card>
            <div className="p-5 flex items-start gap-6 flex-wrap">
              <ScoreRing score={compliance.compliance_score} />
              <div className="flex-1 min-w-0 space-y-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <StatusBadge status={compliance.risk_level} />
                  <span className="text-slate-500 text-xs">
                    {new Date(compliance.created_at).toLocaleString()}
                  </span>
                </div>
                {dashboard && (
                  <div className="grid grid-cols-3 gap-3">
                    {[
                      { label: "Requirements", value: dashboard.requirements_count },
                      { label: "Checklist Items", value: dashboard.checklist_items },
                      { label: "Issues", value: dashboard.issues_count },
                    ].map(({ label, value }) => (
                      <div key={label} className="bg-[#1d2335] rounded-lg p-3 text-center">
                        <p className="text-white text-xl font-bold">{value}</p>
                        <p className="text-slate-400 text-xs mt-0.5">{label}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </Card>

          {/* Issues */}
          {compliance.issues.length > 0 && (
            <Card>
              <CardHeader title="Issues Found" subtitle={`${compliance.issues.length} issue${compliance.issues.length !== 1 ? "s" : ""}`} />
              <div className="divide-y divide-[#2a3347]">
                {compliance.issues.map((issue, i) => (
                  <div key={i} className="px-5 py-3 flex items-start gap-3">
                    <AlertTriangle className="w-4 h-4 text-yellow-400 mt-0.5 flex-shrink-0" />
                    <pre className="text-slate-300 text-xs font-sans whitespace-pre-wrap flex-1">
                      {typeof issue === "string" ? issue : JSON.stringify(issue, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Recommendations */}
          {compliance.recommendations.length > 0 && (
            <Card>
              <CardHeader title="Recommendations" />
              <div className="p-4 space-y-2">
                {compliance.recommendations.map((r, i) => (
                  <div key={i} className="flex items-start gap-3 bg-[#1d2335] rounded-lg px-4 py-3">
                    <CheckCircle className="w-4 h-4 text-indigo-400 mt-0.5 flex-shrink-0" />
                    <p className="text-slate-300 text-sm">{r}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Key dates */}
          {dashboard && dashboard.key_dates.length > 0 && (
            <Card>
              <CardHeader title="Key Dates" />
              <div className="p-4 space-y-2">
                {dashboard.key_dates.map((d, i) => (
                  <div key={i} className="flex items-center gap-3 bg-[#1d2335] rounded-lg px-4 py-3">
                    <CalendarDays className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                    <p className="text-slate-300 text-sm">{JSON.stringify(d)}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Audit breakdown */}
          {audit && (
            <Card>
              <CardHeader title="Agent Outputs" subtitle="Detailed breakdown from each agent" />
              <div className="p-4 space-y-3">
                <Section title="Legal Analysis" icon={Scale} data={audit.legal_output} />
                <Section title="Proposal Generation" icon={FileEdit} data={audit.proposal_output} />
                <Section title="Compliance Audit" icon={ShieldCheck} data={audit.audit_output} />
                <Section title="Final Report" icon={FileOutput} data={audit.final_report} />
              </div>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
