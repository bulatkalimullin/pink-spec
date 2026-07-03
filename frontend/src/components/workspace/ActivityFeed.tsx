import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import { Copy, Download, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { cn, formatTimeAgo } from "@/lib/utils";
import {
  agentsToJson,
  agentsToPlainText,
  formatLogMessage,
  logsToJson,
  logsToPlainText,
} from "@/lib/logFormat";
import { getSessionLogs } from "@/lib/api";
import { useI18n } from "@/i18n/I18nProvider";
import { useSessionStore, LogEntry, AgentState } from "@/stores/sessionStore";
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
  MessageCircleQuestion,
  ListTree,
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
  token_delta: { icon: <Bot className="h-3 w-3" />, label: "Token", badge: "TOK" },
  fallback_triggered: { icon: <AlertTriangle className="h-3 w-3" />, label: "Fallback", badge: "FALLBACK" },
  assumption_logged: { icon: <Eye className="h-3 w-3" />, label: "Assumption", badge: "ASSUME" },
  question_asked: { icon: <MessageCircleQuestion className="h-3 w-3" />, label: "Question", badge: "HITL" },
  intake_started: { icon: <MessageCircleQuestion className="h-3 w-3" />, label: "Intake", badge: "INTAKE" },
  intake_waiting: { icon: <MessageCircleQuestion className="h-3 w-3" />, label: "Intake", badge: "WAIT" },
  intake_complete: { icon: <CheckCircle className="h-3 w-3" />, label: "Intake", badge: "OK" },
  session_stuck: { icon: <AlertTriangle className="h-3 w-3" />, label: "Watchdog", badge: "STUCK" },
  agent_timeout: { icon: <XCircle className="h-3 w-3" />, label: "Timeout", badge: "TIMEOUT" },
  circuit_breaker_open: { icon: <Shield className="h-3 w-3" />, label: "Circuit Breaker", badge: "CB OPEN" },
  circuit_breaker_closed: { icon: <Shield className="h-3 w-3" />, label: "Circuit Breaker", badge: "CB OK" },
  recovery_started: { icon: <RotateCcw className="h-3 w-3" />, label: "Recovery", badge: "RECOVER" },
  checkpoint_saved: { icon: <CheckCircle className="h-3 w-3" />, label: "Checkpoint", badge: "CKPT" },
  artifact_preview: { icon: <FileText className="h-3 w-3" />, label: "Artifact" },
  artifact_patched: { icon: <FileText className="h-3 w-3" />, label: "Artifact", badge: "PATCH" },
  pipeline_planned: { icon: <ListTree className="h-3 w-3" />, label: "Pipeline", badge: "PLAN" },
  completion_check: { icon: <CheckCircle className="h-3 w-3" />, label: "Completion", badge: "L4" },
  session_completed_partial: { icon: <AlertTriangle className="h-3 w-3" />, label: "Partial", badge: "PARTIAL" },
  budget_warning: { icon: <AlertTriangle className="h-3 w-3" />, label: "Budget", badge: "BUDGET" },
  task_batch_generated: { icon: <FileText className="h-3 w-3" />, label: "Tasks", badge: "TASKS" },
  refinement_cycle: { icon: <RotateCcw className="h-3 w-3" />, label: "Review", badge: "REVIEW" },
  error: { icon: <XCircle className="h-3 w-3" />, label: "Error", badge: "ERR" },
  done: { icon: <CheckCircle className="h-3 w-3" />, label: "Done", badge: "DONE" },
  stage_changed: { icon: <Loader2 className="h-3 w-3" />, label: "Этап", badge: "STAGE" },
  saturation_progress: { icon: <Search className="h-3 w-3" />, label: "Контекст", badge: "RAG" },
  summary_updated: { icon: <FileText className="h-3 w-3" />, label: "Summary", badge: "CTX" },
  "worker.session_claimed": { icon: <Bot className="h-3 w-3" />, label: "Worker", badge: "CLAIM" },
  system_warning: { icon: <AlertTriangle className="h-3 w-3" />, label: "System", badge: "SYS" },
};

function getEntryStyle(entry: LogEntry) {
  const level = (entry.payload?.level as string) ?? "info";
  if (entry.type === "log_entry") return LEVEL_STYLES[level] ?? LEVEL_STYLES.info;
  if (
    entry.type === "fallback_triggered" ||
    entry.type === "session_stuck" ||
    entry.type === "agent_timeout" ||
    entry.type === "session_completed_partial" ||
    entry.type === "budget_warning"
  )
    return LEVEL_STYLES.warn;
  if (entry.type === "error") return LEVEL_STYLES.error;
  if (entry.type === "done") return { icon: <CheckCircle className="h-3 w-3" />, cls: "text-pink-400" };
  return LEVEL_STYLES.info;
}

type EntryVisualState = "current" | "completed" | "failed" | "default";

const ROW_STYLES: Record<EntryVisualState, string> = {
  current: "bg-emerald-950/50 border-l-2 border-l-emerald-500 text-emerald-100",
  completed: "bg-pink-950/30 border-l-2 border-l-pink-500/70 text-pink-100",
  failed: "bg-red-950/30 border-l-2 border-l-red-500/70 text-red-200",
  default: "",
};

const AGENT_STATUS_CHIP: Record<AgentState["status"], string> = {
  pending: "bg-zinc-800 text-zinc-400",
  running: "bg-emerald-900/60 text-emerald-300",
  success: "bg-pink-900/50 text-pink-300",
  failed: "bg-red-900/50 text-red-300",
  degraded: "bg-orange-900/50 text-orange-300",
  skipped: "bg-zinc-800 text-zinc-500",
  cancelled: "bg-amber-900/50 text-amber-300",
};

function getAgentId(entry: LogEntry): string {
  const p = entry.payload;
  if (entry.type === "supervisor_routing") return (p?.next_agent as string) ?? "";
  return (p?.agent_id as string) ?? "";
}

function getEntryVisualState(entry: LogEntry, currentAgent: string | null): EntryVisualState {
  const agentId = getAgentId(entry);
  if (entry.type === "agent_completed") {
    const status = entry.payload?.status as string;
    if (status === "success") return "completed";
    if (status === "failed" || status === "cancelled") return "failed";
  }
  if (agentId && currentAgent && agentId === currentAgent) return "current";
  return "default";
}

interface FeedEntryProps {
  entry: LogEntry;
  currentAgent: string | null;
}

function FeedEntry({ entry, currentAgent }: FeedEntryProps) {
  const [expanded, setExpanded] = useState(false);
  const meta = TYPE_META[entry.type] ?? { icon: <Info className="h-3 w-3" />, label: entry.type };
  const style = getEntryStyle(entry);
  const message = formatLogMessage(entry);
  const agentId = getAgentId(entry);
  const visualState = getEntryVisualState(entry, currentAgent);

  const copyLine = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await navigator.clipboard.writeText(formatLogMessage(entry));
    toast.success("Copied");
  };

  return (
    <div
      className={cn(
        "group flex gap-2 px-3 py-1.5 hover:bg-accent/30 cursor-pointer transition-colors border-b border-border/40",
        ROW_STYLES[visualState],
        visualState === "default" && style.cls
      )}
      onClick={() => setExpanded((v) => !v)}
    >
      <div className="mt-0.5 flex-shrink-0">
        {visualState === "current" ? (
          <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />
        ) : visualState === "completed" ? (
          <CheckCircle className="h-3 w-3 text-pink-400" />
        ) : (
          meta.icon ?? style.icon
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs min-w-0">
          {agentId && (
            <span className="font-mono text-[10px] truncate max-w-[100px] text-muted-foreground">
              [{agentId}]
            </span>
          )}
          {meta.badge && visualState === "default" && (
            <span className="rounded border border-current px-1 text-[9px] font-semibold uppercase opacity-70">
              {meta.badge}
            </span>
          )}
          <span className="text-[10px] text-zinc-600">#{entry.seq}</span>
          <span className="text-[10px] text-zinc-600 font-mono hidden sm:inline">{entry.type}</span>
          <div className="flex-1" />
          <button
            type="button"
            onClick={(e) => void copyLine(e)}
            className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-accent"
            title="Copy line"
          >
            <Copy className="h-3 w-3 text-muted-foreground" />
          </button>
          <span className="text-[10px] text-zinc-600 hidden group-hover:block">{formatTimeAgo(entry.ts)}</span>
          {expanded ? <ChevronUp className="h-3 w-3 opacity-40" /> : <ChevronDown className="h-3 w-3 opacity-0 group-hover:opacity-40" />}
        </div>
        <p className="text-xs leading-relaxed break-words min-w-0">{message}</p>
        {expanded && (
          <pre className="mt-1.5 rounded bg-zinc-900 p-2 text-[10px] font-mono text-zinc-400 overflow-x-auto select-all">
            {JSON.stringify({ seq: entry.seq, type: entry.type, ts: entry.ts, payload: entry.payload }, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

type FilterLevel = "all" | "info" | "warn" | "error";

interface ActivityFeedProps {
  sessionId?: string;
}

export default function ActivityFeed({ sessionId }: ActivityFeedProps) {
  const { t } = useI18n();
  const logs = useSessionStore((s) => s.logs);
  const replaceLogs = useSessionStore((s) => s.replaceLogs);
  const agents = useSessionStore((s) => s.agents);
  const pipeline = useSessionStore((s) => s.pipeline);
  const currentAgent = useSessionStore((s) => s.currentAgent);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<FilterLevel>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [statesExpanded, setStatesExpanded] = useState(true);

  const loadFullLogs = useCallback(async () => {
    if (!sessionId) return;
    setLoadingLogs(true);
    try {
      const { logs: remote } = await getSessionLogs(sessionId, 0, 5000);
      replaceLogs(
        (remote as LogEntry[]).map((e) => ({
          seq: Number(e.seq),
          type: String(e.type),
          ts: String(e.ts),
          session_id: sessionId,
          payload: (e.payload as Record<string, unknown>) ?? {},
        }))
      );
      toast.success(t.workspace.logsReloaded.replace("{count}", String(remote.length)));
    } catch {
      toast.error(t.workspace.logsReloadFailed);
    } finally {
      setLoadingLogs(false);
    }
  }, [sessionId, replaceLogs, t.workspace]);

  useEffect(() => {
    if (sessionId) void loadFullLogs();
  }, [sessionId, loadFullLogs]);

  const filtered = useMemo(() => {
    if (filter === "all") return logs;
    return logs.filter((e) => {
      const level = (e.payload?.level as string) ?? "";
      if (filter === "info") return true;
      if (filter === "warn")
        return (
          ["warn", "error"].includes(level) ||
          [
            "fallback_triggered",
            "session_stuck",
            "budget_warning",
            "session_completed_partial",
          ].includes(e.type)
        );
      if (filter === "error")
        return level === "error" || e.type === "error" || e.type === "agent_timeout";
      return true;
    });
  }, [logs, filter]);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [filtered.length, autoScroll]);

  const copyLogs = async () => {
    await navigator.clipboard.writeText(logsToPlainText(filtered));
    toast.success(t.workspace.logsCopied);
  };

  const copyJson = async () => {
    await navigator.clipboard.writeText(logsToJson(filtered));
    toast.success(t.workspace.jsonCopied);
  };

  const copyStates = async () => {
    const text = `${agentsToPlainText(agents, pipeline, currentAgent)}\n\n--- JSON ---\n${agentsToJson(agents, currentAgent)}`;
    await navigator.clipboard.writeText(text);
    toast.success(t.workspace.statesCopied);
  };

  const pipelineIds = pipeline.length > 0 ? pipeline.map((s) => s.id) : Object.keys(agents);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-shrink-0 flex-wrap items-center gap-1.5 border-b border-border px-2 py-1.5">
        <span className="text-xs font-medium text-muted-foreground">{t.workspace.activityTitle}</span>
        <span className="text-xs text-zinc-600">({filtered.length}/{logs.length})</span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => void copyLogs()}
          disabled={filtered.length === 0}
          className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-accent disabled:opacity-40"
        >
          <Copy className="h-3 w-3" />
          {t.workspace.copyLogs}
        </button>
        <button
          type="button"
          onClick={() => void copyJson()}
          disabled={filtered.length === 0}
          className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-accent disabled:opacity-40"
        >
          <Download className="h-3 w-3" />
          {t.workspace.copyJson}
        </button>
        <button
          type="button"
          onClick={() => void loadFullLogs()}
          disabled={!sessionId || loadingLogs}
          className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-accent disabled:opacity-40"
        >
          <RefreshCw className={cn("h-3 w-3", loadingLogs && "animate-spin")} />
          {t.workspace.reloadLogs}
        </button>
        {(["all", "info", "warn", "error"] as FilterLevel[]).map((f) => (
          <button
            key={f}
            type="button"
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
          type="button"
          onClick={() => setAutoScroll((a) => !a)}
          className={cn(
            "rounded px-2 py-0.5 text-[11px] transition-colors",
            autoScroll ? "text-primary" : "text-muted-foreground"
          )}
        >
          Auto ↓
        </button>
      </div>

      <div className="flex-shrink-0 border-b border-border bg-card/30">
        <div className="flex items-center gap-2 px-3 py-1.5">
          <button
            type="button"
            className="flex flex-1 items-center gap-2 text-left text-[10px] font-medium text-muted-foreground hover:text-foreground"
            onClick={() => setStatesExpanded((v) => !v)}
          >
            {statesExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {t.workspace.agentStates}
          </button>
          <button
            type="button"
            onClick={() => void copyStates()}
            className="inline-flex items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[10px] hover:bg-accent"
          >
            <Copy className="h-3 w-3" />
            {t.workspace.copyStates}
          </button>
        </div>
        {statesExpanded && (
          <div className="flex flex-wrap gap-1 px-3 pb-2 max-h-24 overflow-y-auto">
            {pipelineIds.map((id) => {
              const a = agents[id];
              const status = a?.status ?? "pending";
              const isCurrent = currentAgent === id;
              return (
                <span
                  key={id}
                  title={a?.name ?? id}
                  className={cn(
                    "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-mono",
                    AGENT_STATUS_CHIP[status],
                    isCurrent && "ring-1 ring-emerald-500"
                  )}
                >
                  {isCurrent && <Loader2 className="h-2.5 w-2.5 animate-spin" />}
                  {id}
                  <span className="opacity-70">{status}</span>
                </span>
              );
            })}
            {pipelineIds.length === 0 && (
              <span className="text-[10px] text-zinc-600">—</span>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto" onScroll={() => setAutoScroll(false)}>
        {filtered.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-zinc-600">
            {t.workspace.waitingEvents}
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
