"use client";

import { useState } from "react";
import { Search, ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { Card, CardHeader } from "@/components/Card";

export default function ReportsIndexPage() {
  const [tenderId, setTenderId] = useState("");
  const router = useRouter();

  function go() {
    if (tenderId.trim()) router.push(`/reports/${encodeURIComponent(tenderId.trim())}`);
  }

  return (
    <div className="p-6 max-w-2xl">
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Reports</h1>
        <p className="text-slate-400 text-sm mt-1">View compliance and audit reports for a tender</p>
      </div>
      <Card>
        <CardHeader title="Look up a Tender" subtitle="Enter a Tender ID to view its latest analysis" />
        <div className="p-5">
          <div className="flex gap-3">
            <input
              value={tenderId}
              onChange={(e) => setTenderId(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && go()}
              placeholder="e.g. TENDER-2024-001"
              className="flex-1 bg-[#0f1117] border border-[#2a3347] rounded-lg px-3 py-2.5 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
            <button
              onClick={go}
              disabled={!tenderId.trim()}
              className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white text-sm font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Search className="w-4 h-4" />
              View
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
