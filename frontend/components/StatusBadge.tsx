import clsx from "clsx";

interface Props {
  status: string;
  size?: "sm" | "md";
}

const statusMap: Record<string, { label: string; dot: string; text: string }> = {
  ok:       { label: "OK",       dot: "bg-emerald-400", text: "text-emerald-400" },
  healthy:  { label: "Healthy",  dot: "bg-emerald-400", text: "text-emerald-400" },
  ready:    { label: "Ready",    dot: "bg-emerald-400", text: "text-emerald-400" },
  completed:{ label: "Done",     dot: "bg-emerald-400", text: "text-emerald-400" },
  processed:{ label: "Processed",dot: "bg-emerald-400", text: "text-emerald-400" },
  degraded: { label: "Degraded", dot: "bg-yellow-400",  text: "text-yellow-400" },
  pending:  { label: "Pending",  dot: "bg-yellow-400",  text: "text-yellow-400" },
  running:  { label: "Running",  dot: "bg-blue-400 animate-pulse", text: "text-blue-400" },
  processing:{ label: "Processing", dot: "bg-blue-400 animate-pulse", text: "text-blue-400" },
  error:    { label: "Error",    dot: "bg-red-400",     text: "text-red-400" },
  failed:   { label: "Failed",   dot: "bg-red-400",     text: "text-red-400" },
  low:      { label: "Low",      dot: "bg-emerald-400", text: "text-emerald-400" },
  medium:   { label: "Medium",   dot: "bg-yellow-400",  text: "text-yellow-400" },
  high:     { label: "High",     dot: "bg-orange-400",  text: "text-orange-400" },
  critical: { label: "Critical", dot: "bg-red-400",     text: "text-red-400" },
};

export default function StatusBadge({ status, size = "md" }: Props) {
  const s = statusMap[status.toLowerCase()] ?? { label: status, dot: "bg-slate-400", text: "text-slate-400" };
  return (
    <span className={clsx("inline-flex items-center gap-1.5 font-medium", size === "sm" ? "text-xs" : "text-sm")}>
      <span className={clsx("rounded-full flex-shrink-0", s.dot, size === "sm" ? "w-1.5 h-1.5" : "w-2 h-2")} />
      <span className={s.text}>{s.label}</span>
    </span>
  );
}
