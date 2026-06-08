"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, FileSearch, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import type { ChatMessage, SourceItem } from "@/lib/types";
import { Card } from "@/components/Card";

function renderAnswer(text: string) {
  return text.split("\n").map((line, i) => (
    <span key={i}>
      {line}
      {i < text.split("\n").length - 1 && <br />}
    </span>
  ));
}

function SourcesPanel({ sources }: { sources: SourceItem[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;
  return (
    <div className="mt-3 border border-[#2a3347] rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 bg-[#1d2335] text-slate-400 text-xs hover:bg-[#252f47] transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <FileSearch className="w-3.5 h-3.5" />
          {sources.length} source{sources.length !== 1 ? "s" : ""}
        </span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <div className="divide-y divide-[#2a3347]">
          {sources.map((s, i) => (
            <div key={i} className="px-3 py-2 bg-[#161b27]">
              <div className="flex items-center justify-between">
                <span className="text-slate-400 text-xs font-mono truncate max-w-48">
                  {s.document_id?.slice(0, 12) ?? "—"}…
                </span>
                {s.page_number != null && (
                  <span className="text-slate-500 text-xs">p.{s.page_number}</span>
                )}
                <span className="text-indigo-400 text-xs font-mono">
                  {(s.score * 100).toFixed(1)}%
                </span>
              </div>
              {s.chunk_id && (
                <p className="text-slate-600 text-xs font-mono mt-0.5">chunk: {s.chunk_id.slice(0, 12)}…</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function QueryPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [tenderId, setTenderId] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    const userMsg: ChatMessage = { role: "user", content: q, timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    try {
      const res = await api.ragQuery(q, tenderId || undefined);
      const botMsg: ChatMessage = {
        role: "assistant",
        content: res.answer,
        sources: res.sources,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (e) {
      const errMsg: ChatMessage = {
        role: "assistant",
        content: `Error: ${(e as Error).message}`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="flex flex-col h-screen p-6">
      <div className="mb-4">
        <h1 className="text-white text-2xl font-bold">RAG Query</h1>
        <p className="text-slate-400 text-sm mt-1">Ask questions about your procurement documents</p>
      </div>

      {/* Tender filter */}
      <div className="flex items-center gap-3 mb-4">
        <label className="text-slate-400 text-sm flex-shrink-0">Tender ID (optional)</label>
        <input
          value={tenderId}
          onChange={(e) => setTenderId(e.target.value)}
          placeholder="Filter by tender ID…"
          className="bg-[#161b27] border border-[#2a3347] rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors w-64"
        />
      </div>

      {/* Chat */}
      <Card className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center py-16">
              <Bot className="w-12 h-12 text-slate-600 mb-4" />
              <p className="text-slate-400 text-base font-medium">Ask anything about your procurement documents</p>
              <p className="text-slate-600 text-sm mt-2">Questions about compliance, requirements, deadlines, terms…</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
              <div
                className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                  msg.role === "user" ? "bg-indigo-600" : "bg-[#1d2335]"
                }`}
              >
                {msg.role === "user" ? (
                  <User className="w-4 h-4 text-white" />
                ) : (
                  <Bot className="w-4 h-4 text-indigo-400" />
                )}
              </div>
              <div className={`max-w-[75%] ${msg.role === "user" ? "items-end" : "items-start"} flex flex-col`}>
                <div
                  className={`px-4 py-3 rounded-xl text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-indigo-600 text-white"
                      : "bg-[#1d2335] text-slate-200"
                  }`}
                >
                  {renderAnswer(msg.content)}
                </div>
                {msg.sources && <SourcesPanel sources={msg.sources} />}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="w-7 h-7 rounded-full bg-[#1d2335] flex items-center justify-center flex-shrink-0">
                <Bot className="w-4 h-4 text-indigo-400" />
              </div>
              <div className="px-4 py-3 bg-[#1d2335] rounded-xl">
                <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-[#2a3347] p-4">
          <div className="flex items-end gap-3">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask a question… (Enter to send, Shift+Enter for new line)"
              rows={2}
              className="flex-1 bg-[#0f1117] border border-[#2a3347] rounded-xl px-4 py-3 text-white text-sm placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors resize-none"
            />
            <button
              onClick={send}
              disabled={!input.trim() || loading}
              className="flex items-center justify-center w-10 h-10 bg-indigo-600 hover:bg-indigo-500 rounded-xl text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
