import { useRef, useEffect, useState, useMemo } from "react";
import { cn, formatTimeAgo } from "@/lib/utils";
import { useSessionStore, LogEntry } from "@/stores/sessionStore";
import {
  AlertTriangle,
  Bot,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Info,
  XCircle,
  Zap,
  GitBranch,
  Eye,
  FileText,
  Shield,
  RotateCcw,
  Loader2,
  Search,
} from "lucide-react";

const LEVEL_STYLES: Record<string, { icon: React.ReactNode; cls: string }> = {
  debug: { icon: <Info className="h-3 w-3" />, cls: "text-zinc-500" },
  info: { icon: <Info className="h-3 w-3" />, cls: "text-zinc-300" },
  warn: { icon: <AlertTriangle className="h-3 w-3" />, cls: "text-amber-400" },
  error: { icon: <XCircle className="h-3 w-3" />, cls: "text-red-400" },
};

const TYPE_META: Record<string, { icon: React.ReactNode; label: string; badge?: string }> = {
  log_entry: { icon: <Bot className="h-3 w-3" />, label: "Log" },
  supervisor_routing: { icon: <GitBranch className="h-3 w-3" />, label: "Supervisor", badge: "ROUTE" },
  agent_started: { icon: <Zap className="h-3 w-3" />, label: "Agent", badge: "START" },
  agent_completed: { icon: <CheckCircle className="h-3 w-3" />, label: "Agent", badge: "DONE" },
  fallback_triggered: { icon: <AlertTriangle className="h-3 w-3" />, label: "Fallback", badge: "FALLBACK" },
  assumption_logged: { icon: <Eye className="h-3 w-3" />, label: "Assumption", badge: "ASSUME" },
  session_stuck: { icon: <AlertTriangle className="h-3 w-3" />, label: "Watchdog", badge: "STUCK" },
  agent_timeout: { icon: <XCircle className="h-3 w-3" />, label: "Timeout", badge: "TIMEOUT" },
  circuit_breaker_open: { icon: <Shield className="h-3 w-3" />, label: "Circuit Breaker", badge: "CB OPEN" },
  circuit_breaker_closed: { icon: <Shield className="h-3 w-3" />, label: "Circuit Breaker", badge: "CB OK" },
  recovery_started: { icon: <RotateCcw className="h-3 w-3" />, label: "Recovery", badge: "RECOVER" },
  checkpoint_saved: { icon: <CheckCircle className="h-3 w-3" />, label: "Checkpoint", badge: "CKPT" },
  artifact_preview: { icon: <FileText className="h-3 w-3" />, label: "Artifact" },
  done: { icon: <CheckCircle className="h-3 w-3" />, label: "Done", badge: "DONE" },
  stage_changed: { icon: <Loader2 className="h-3 w-3" />, label: "Этап", badge: "STAGE" },
  saturation_progress: { icon: <Search className="h-3 w-3" />, label: "Контекст", badge: "RAG" },
};

function getEntryStyle(entry: LogEntry) {
  const level = (entry.payload?.level as string) ?? "info";
  if (entry.type === "log_entry") return LEVEL_STYLES[level] ?? LEVEL_STYLES.info;
  if (entry.type === "fallback_triggered" || entry.type === "session_stuck" || entry.type === "agent_timeout")
    return LEVEL_STYLES.warn;
  if (entry.type === "error") return LEVEL_STYLES.error;
  if (entry.type === "done") return { icon: <CheckCircle className="h-3 w-3" />, cls: "text-pink-400" };
  return LEVEL_STYLES.info;
}

function getEntryMessage(entry: LogEntry): string {
  const p = entry.payload;
  switch (entry.type) {
    case "log_entry": return (p?.message as string) ?? "";
    case "supervisor_routing": return `Route → ${p?.next_agent} — ${p?.reason}`;
    case "agent_started": return `${p?.agent_name} started (pass #${p?.pass_number})`;
    case "agent_completed": return `${p?.agent_id} completed in ${p?.duration_ms}ms — ${p?.status}`;
    case "fallback_triggered": return `[${p?.layer}] ${p?.message}`;
    case "assumption_logged": return `[${p?.agent_id}] ${p?.text}`;
    case "session_stuck": return `Stuck: ${p?.reason} (${p?.since_sec}s)`;
    case "agent_timeout": return `${p?.agent_id} timed out after ${p?.timeout_sec}s`;
    case "circuit_breaker_open": return `Circuit breaker OPEN for ${p?.agent_id}`;
    case "circuit_breaker_closed": return `Circuit breaker CLOSED for ${p?.agent_id}`;
    case "recovery_started": return `Recovery: ${p?.action} on ${p?.target_agent ?? "session"}`;
    case "checkpoint_saved": return `Checkpoint saved: ${p?.checkpoint_id}`;
    case "artifact_preview": return `${p?.artifact_type} preview…`;
    case "done": return `Complete! ${p?.artifacts_count} artifacts, ${p?.tasks_count} tasks`;
    case "stage_changed": {
      const detail = p?.detail ? ` — ${p.detail}` : "";
      const eta = p?.eta_sec != null ? ` · ≈${Math.round((p.eta_sec as number) / 60)} мин` : "";
      return `${p?.label}${detail} (${p?.percent}%)${eta}`;
    }
    case "saturation_progress":
      return `Собираем контекст: итерация ${p?.iteration}, ${p?.chunks} фрагментов`;
    default: return JSON.stringify(p).slice(0, 120);
  }
}

type EntryVisualState = "current" | "completed" | "failed" | "default";

const ROW_STYLES: Record<EntryVisualState, string> = {
  current:
    "bg-emerald-950/50 border-l-2 border-l-emerald-500 text-emerald-100",
  completed:
    "bg-pink-950/30 border-l-2 border-l-pink-500/70 text-pink-100",
  failed:
    "bg-red-950/30 border-l-2 border-l-red-500/70 text-red-200",
  default: "",
};

function getAgentId(entry: LogEntry): string {
  const p = entry.payload;
  if (entry.type === "supervisor_routing") {
    return (p?.next_agent as string) ?? "";
  }
  return (p?.agent_id as string) ?? "";
}

function getEntryVisualState(
  entry: LogEntry,
  currentAgent: string | null,
): EntryVisualState {
  const agentId = getAgentId(entry);

  if (entry.type === "agent_completed") {
    const status = entry.payload?.status as string;
    if (status === "success") return "completed";
    if (status === "failed" || status === "cancelled") return "failed";
  }

  if (agentId && currentAgent && agentId === currentAgent) {
    return "current";
  }

  return "default";
}

interface FeedEntryProps {
  entry: LogEntry;
  currentAgent: string | null;
}

function FeedEntry({ entry, currentAgent }: FeedEntryProps) {
  const [expanded, setExpanded] = useState(false);
  const meta = TYPE_META[entry.type];
  const style = getEntryStyle(entry);
  const message = getEntryMessage(entry);
  const agentId = getAgentId(entry);
  const visualState = getEntryVisualState(entry, currentAgent);
  const timeLabel = formatTimeAgo(entry.ts);

  return (
    <div
      className={cn(
        "group flex gap-2 px-3 py-1.5 hover:bg-accent/30 cursor-pointer transition-colors border-b border-border/40",
        ROW_STYLES[visualState],
        visualState === "default" && style.cls
      )}
      onClick={() => setExpanded((e) => !e)}
    >
      {/* Icon */}
      <div className="mt-0.5 flex-shrink-0">
        {visualState === "current" ? (
          <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
        ) : visualState === "completed" ? (
          <CheckCircle className="h-3 w-3 text-pink-400" />
        ) : (
          meta?.icon ?? style.icon
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs min-w-0">
          {agentId && (
            <span
              className={cn(
                "font-mono text-[10px] truncate max-w-[100px]",
                visualState === "current"
                  ? "text-emerald-300 font-semibold"
                  : visualState === "completed"
                    ? "text-pink-300"
                    : "text-muted-foreground"
              )}
            >
              [{agentId}]
            </span>
          )}
          {visualState === "current" && (
            <span className="rounded bg-emerald-500/20 px-1 text-[9px] font-semibold uppercase text-emerald-300">
              RUN
            </span>
          )}
          {visualState === "completed" && entry.type === "agent_completed" && (
            <span className="rounded bg-pink-500/20 px-1 text-[9px] font-semibold uppercase text-pink-300">
              OK
            </span>
          )}
          {/* Type badge */}
          {meta?.badge && visualState === "default" && (
            <span className="rounded border border-current px-1 text-[9px] font-semibold uppercase opacity-70">
              {meta.badge}
            </span>
          )}
          {/* seq */}
          <span className="text-[10px] text-zinc-600">#{entry.seq}</span>
          <div className="flex-1" />
          <span className="text-[10px] text-zinc-600 hidden group-hover:block">{timeLabel}</span>
          {expanded ? (
            <ChevronUp className="h-3 w-3 opacity-40" />
          ) : (
            <ChevronDown className="h-3 w-3 opacity-0 group-hover:opacity-40" />
          )}
        </div>
        <p className="text-xs leading-relaxed break-words min-w-0">{message}</p>
        {expanded && (
          <pre className="mt-1.5 rounded bg-zinc-900 p-2 text-[10px] font-mono text-zinc-400 overflow-x-auto">
            {JSON.stringify(entry.payload, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

type FilterLevel = "all" | "info" | "warn" | "error";

export default function ActivityFeed() {
  const logs = useSessionStore((s) => s.logs);
  const currentAgent = useSessionStore((s) => s.currentAgent);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<FilterLevel>("all");
  const [autoScroll, setAutoScroll] = useState(true);

  const filtered = useMemo(() => {
    if (filter === "all") return logs;
    return logs.filter((e) => {
      const level = (e.payload?.level as string) ?? "";
      if (filter === "info") return true;
      if (filter === "warn") return ["warn", "error"].includes(level) || e.type === "fallback_triggered" || e.type === "session_stuck";
      if (filter === "error") return level === "error" || e.type === "error" || e.type === "agent_timeout";
      return true;
    });
  }, [logs, filter]);

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [filtered.length, autoScroll]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Toolbar */}
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-1.5">
        <span className="text-xs text-muted-foreground font-medium">Activity</span>
        <span className="text-xs text-zinc-600">({filtered.length})</span>
        <span className="hidden sm:inline text-[10px] text-zinc-600">
          <span className="text-emerald-400">●</span> run
          <span className="mx-1.5 text-pink-400">●</span> done
        </span>
        <div className="flex-1" />
        {(["all", "info", "warn", "error"] as FilterLevel[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded px-2 py-0.5 text-[11px] font-medium capitalize transition-colors",
              filter === f ? "bg-primary/20 text-primary" : "text-muted-foreground hover:text-foreground"
            )}
          >
            {f}
          </button>
        ))}
        <button
          onClick={() => setAutoScroll((a) => !a)}
          className={cn(
            "rounded px-2 py-0.5 text-[11px] transition-colors",
            autoScroll ? "text-primary" : "text-muted-foreground"
          )}
        >
          Auto ↓
        </button>
      </div>

      {/* Feed */}
      <div className="flex-1 min-h-0 overflow-y-auto" onScroll={() => setAutoScroll(false)}>
        {filtered.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-zinc-600">
            Waiting for events…
          </div>
        ) : (
          filtered.map((entry) => (
            <FeedEntry key={entry.seq} entry={entry} currentAgent={currentAgent} />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
