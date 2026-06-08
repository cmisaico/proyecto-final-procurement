"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileText,
  MessageSquare,
  GitFork,
  BarChart3,
  DollarSign,
  Cpu,
} from "lucide-react";
import clsx from "clsx";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/query", label: "RAG Query", icon: MessageSquare },
  { href: "/workflow", label: "Workflow", icon: GitFork },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/cost", label: "Cost Analysis", icon: DollarSign },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex flex-col w-60 min-h-screen bg-[#161b27] border-r border-[#2a3347]">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-[#2a3347]">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-600">
          <Cpu className="w-4 h-4 text-white" />
        </div>
        <div>
          <p className="text-white font-semibold text-sm leading-none">Procurement</p>
          <p className="text-indigo-400 text-xs mt-0.5">Intelligence Platform</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 px-3 py-4 flex-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                active
                  ? "bg-indigo-600/20 text-indigo-300 font-medium"
                  : "text-slate-400 hover:bg-[#1d2335] hover:text-slate-200"
              )}
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[#2a3347]">
        <p className="text-xs text-slate-500">Fase 4 · Kubernetes</p>
        <p className="text-xs text-slate-600">Qwen2.5:7b + RTX 5080</p>
      </div>
    </aside>
  );
}
