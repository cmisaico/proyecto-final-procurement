"use client";

import { useState, useRef } from "react";
import { Upload, FileText, CheckCircle, Loader2, AlertCircle, Cpu, Hash } from "lucide-react";
import { api } from "@/lib/api";
import type { UploadResponse, ProcessResponse } from "@/lib/types";
import { Card, CardHeader } from "@/components/Card";
import StatusBadge from "@/components/StatusBadge";

interface DocEntry {
  upload: UploadResponse;
  process?: ProcessResponse;
  processing?: boolean;
  error?: string;
}

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const [tenderId, setTenderId] = useState("");
  const [docs, setDocs] = useState<DocEntry[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    if (!tenderId.trim()) {
      setUploadError("Please enter a Tender ID first");
      return;
    }
    setUploadError(null);
    setUploading(true);
    for (const file of Array.from(files)) {
      try {
        const upload = await api.uploadDocument(tenderId.trim(), file);
        setDocs((prev) => [...prev, { upload }]);
      } catch (e) {
        setUploadError((e as Error).message);
      }
    }
    setUploading(false);
  }

  async function processDoc(idx: number) {
    const entry = docs[idx];
    setDocs((prev) => prev.map((d, i) => (i === idx ? { ...d, processing: true, error: undefined } : d)));
    try {
      const process = await api.processDocument(entry.upload.document_id);
      setDocs((prev) => prev.map((d, i) => (i === idx ? { ...d, process, processing: false } : d)));
    } catch (e) {
      setDocs((prev) =>
        prev.map((d, i) => (i === idx ? { ...d, processing: false, error: (e as Error).message } : d))
      );
    }
  }

  return (
    <div className="p-6 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Documents</h1>
        <p className="text-slate-400 text-sm mt-1">Upload procurement PDFs and index them for RAG queries</p>
      </div>

      {/* Upload area */}
      <Card className="mb-6">
        <CardHeader title="Upload Document" subtitle="Accepted: PDF files" />
        <div className="p-5 space-y-4">
          <div>
            <label className="text-slate-300 text-sm font-medium block mb-1.5">Tender ID</label>
            <input
              value={tenderId}
              onChange={(e) => setTenderId(e.target.value)}
              placeholder="e.g. TENDER-2024-001"
              className="w-full bg-[#0f1117] border border-[#2a3347] rounded-lg px-3 py-2.5 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
            onClick={() => fileRef.current?.click()}
            className={`flex flex-col items-center justify-center gap-3 p-10 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
              dragOver ? "border-indigo-500 bg-indigo-500/5" : "border-[#2a3347] hover:border-[#3d5071] hover:bg-[#1d2335]"
            }`}
          >
            {uploading ? (
              <Loader2 className="w-8 h-8 text-indigo-400 animate-spin" />
            ) : (
              <Upload className="w-8 h-8 text-slate-500" />
            )}
            <div className="text-center">
              <p className="text-slate-300 text-sm font-medium">
                {uploading ? "Uploading…" : "Drop PDF here or click to browse"}
              </p>
              <p className="text-slate-500 text-xs mt-1">Supports single or multiple files</p>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,application/pdf"
              multiple
              className="hidden"
              onChange={(e) => handleFiles(e.target.files)}
            />
          </div>

          {uploadError && (
            <div className="flex items-center gap-2 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {uploadError}
            </div>
          )}
        </div>
      </Card>

      {/* Uploaded documents */}
      {docs.length > 0 && (
        <Card>
          <CardHeader title="Uploaded Documents" subtitle={`${docs.length} file${docs.length !== 1 ? "s" : ""} this session`} />
          <div className="divide-y divide-[#2a3347]">
            {docs.map((entry, idx) => (
              <div key={entry.upload.document_id} className="p-4 flex items-start gap-4">
                <div className="p-2 bg-indigo-500/10 rounded-lg mt-0.5">
                  <FileText className="w-5 h-5 text-indigo-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm font-medium truncate">{entry.upload.filename}</p>
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    <span className="text-slate-500 text-xs font-mono">{entry.upload.document_id.slice(0, 8)}…</span>
                    <span className="text-slate-500 text-xs">{formatBytes(entry.upload.file_size)}</span>
                    <span className="text-slate-500 text-xs">Tender: {entry.upload.tender_id}</span>
                  </div>
                  {entry.process && (
                    <div className="flex items-center gap-4 mt-2">
                      <span className="text-emerald-400 text-xs flex items-center gap-1">
                        <CheckCircle className="w-3 h-3" /> {entry.process.page_count} pages
                      </span>
                      <span className="text-emerald-400 text-xs flex items-center gap-1">
                        <Hash className="w-3 h-3" /> {entry.process.chunk_count} chunks
                      </span>
                      <StatusBadge status={entry.process.status} size="sm" />
                    </div>
                  )}
                  {entry.error && (
                    <p className="text-red-400 text-xs mt-1">{entry.error}</p>
                  )}
                </div>
                <div className="flex-shrink-0">
                  {entry.process ? (
                    <StatusBadge status="processed" />
                  ) : (
                    <button
                      onClick={() => processDoc(idx)}
                      disabled={entry.processing}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-white text-xs font-medium transition-colors disabled:opacity-50"
                    >
                      {entry.processing ? (
                        <><Loader2 className="w-3 h-3 animate-spin" /> Processing…</>
                      ) : (
                        <><Cpu className="w-3 h-3" /> Process & Index</>
                      )}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
