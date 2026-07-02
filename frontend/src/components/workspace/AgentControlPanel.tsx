import { useEffect, useState } from "react";
import {
  AlertTriangle,
  Download,
  GitBranch,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Settings2,
  SkipForward,
  Square,
  Target,
} from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";
import {
  exportSession,
  getSessionControl,
  recoverSession,
  restartSession,
  sendSessionControl,
} from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
}

const STATUS_LABELS: Record<string, string> = {
  pending: "Ожидание",
  running: "Работает",
  waiting_user: "Ждёт ответы",
  paused: "На паузе",
  stuck: "Застряла",
  interrupted: "Прервана",
  degraded: "Деградация",
  completed: "Завершена",
  completed_partial: "Частично",
  failed: "Ошибка",
};

const STATUS_COLORS: Record<string, string> = {
  running: "bg-emerald-900/40 text-emerald-300",
  waiting_user: "bg-sky-900/40 text-sky-300",
  paused: "bg-zinc-800 text-zinc-300",
  stuck: "bg-amber-900/40 text-amber-300",
  interrupted: "bg-orange-900/40 text-orange-300",
  degraded: "bg-orange-900/40 text-orange-300",
  completed: "bg-emerald-900/40 text-emerald-300",
  completed_partial: "bg-amber-900/40 text-amber-300",
  failed: "bg-red-900/40 text-red-300",
};

export default function AgentControlPanel({ sessionId }: Props) {
  const {
    specLevel,
    sessionStatus,
    reviewCycles,
    l4Criteria,
    isStuck,
    stuckReason,
    currentAgent,
    circuitBreakers,
  } = useSessionStore();

  const [maxReviewCycles, setMaxReviewCycles] = useState(10);
  const [completionConfidence, setCompletionConfidence] = useState(0.85);
  const [untilConfident, setUntilConfident] = useState(true);
  const [loading, setLoading] = useState<string | null>(null);

  const isActive = ["running", "degraded", "waiting_user", "paused", "stuck"].includes(
    sessionStatus
  );
  const canControl = ["running", "degraded", "paused", "stuck", "waiting_user"].includes(
    sessionStatus
  );
  const canRestart = ["interrupted", "stuck", "completed_partial", "failed", "degraded"].includes(
    sessionStatus
  );
  const openCBs = Object.keys(circuitBreakers).filter((k) => circuitBreakers[k]);

  useEffect(() => {
    if (!sessionId) return;
    getSessionControl(sessionId)
      .then((cfg) => {
        setMaxReviewCycles(cfg.max_review_cycles);
        setCompletionConfidence(cfg.completion_confidence);
        setUntilConfident(cfg.until_confident);
      })
      .catch(() => {});
  }, [sessionId]);

  const runControl = async (action?: string) => {
    setLoading(action ?? "settings");
    try {
      await sendSessionControl(sessionId, {
        max_review_cycles: maxReviewCycles,
        completion_confidence: completionConfidence,
        until_confident: untilConfident,
        action,
      });
      toast.success(action ? `Команда отправлена: ${action}` : "Настройки применены");
    } catch (e) {
      toast.error("Не удалось выполнить команду", { description: String(e) });
    } finally {
      setLoading(null);
    }
  };

  const runRecovery = async (action: string) => {
    setLoading(action);
    try {
      await recoverSession(sessionId, action, currentAgent ?? undefined);
      toast.success(`Recovery: ${action}`);
    } catch (e) {
      toast.error("Recovery failed", { description: String(e) });
    } finally {
      setLoading(null);
    }
  };

  const runRestart = async () => {
    setLoading("restart");
    try {
      await restartSession(sessionId);
      useSessionStore.setState({ sessionStatus: "running", isStuck: false, stuckReason: null });
      toast.success("Пайплайн перезапущен");
    } catch (e) {
      toast.error("Не удалось перезапустить", { description: String(e) });
    } finally {
      setLoading(null);
    }
  };

  const handlePartialExport = async () => {
    setLoading("export");
    try {
      const blob = await exportSession(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pink-spec-${sessionId.slice(0, 8)}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error("Export failed", { description: String(e) });
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-3">
      <div className="flex items-center gap-2">
        <Settings2 className="h-4 w-4 text-pink-400" />
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Управление агентом
        </p>
        <span
          className={cn(
            "ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold",
            STATUS_COLORS[sessionStatus] ?? "bg-zinc-800 text-zinc-400"
          )}
        >
          {STATUS_LABELS[sessionStatus] ?? sessionStatus}
        </span>
      </div>

      {currentAgent && (
        <p className="text-[10px] text-muted-foreground">
          Текущий агент: <span className="font-mono text-foreground">{currentAgent}</span>
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {sessionStatus === "paused" ? (
          <button
            disabled={!!loading}
            onClick={() => void runControl("resume")}
            className="flex items-center gap-1.5 rounded border border-emerald-700/50 px-2.5 py-1.5 text-xs text-emerald-300 hover:bg-emerald-900/30 disabled:opacity-50"
          >
            {loading === "resume" ? (
              <RefreshCw className="h-3 w-3 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            Продолжить
          </button>
        ) : (
          canControl && (
            <button
              disabled={!!loading || sessionStatus === "waiting_user"}
              onClick={() => void runControl("pause")}
              className="flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
            >
              {loading === "pause" ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <Pause className="h-3.5 w-3.5" />
              )}
              Пауза
            </button>
          )
        )}
        {canControl && (
          <>
            <button
              disabled={!!loading}
              onClick={() => void runControl("cancel")}
              className="flex items-center gap-1.5 rounded border border-red-800/50 px-2.5 py-1.5 text-xs text-red-300 hover:bg-red-900/30 disabled:opacity-50"
            >
              {loading === "cancel" ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <Square className="h-3.5 w-3.5" />
              )}
              Отменить
            </button>
            <button
              disabled={!!loading}
              onClick={() => void runControl("force_export")}
              className="flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
            >
              {loading === "force_export" ? (
                <RefreshCw className="h-3 w-3 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              Force Export
            </button>
          </>
        )}
      </div>

      {canRestart && (
        <div className="rounded border border-orange-700/40 bg-orange-900/10 p-2 space-y-2">
          <p className="text-xs text-orange-300">
            Пайплайн остановлен. Перезапустите, чтобы продолжить с сохранёнными ответами.
          </p>
          <button
            disabled={!!loading}
            onClick={() => void runRestart()}
            className="flex items-center gap-1.5 rounded border border-orange-700/50 px-2.5 py-1.5 text-xs text-orange-200 hover:bg-orange-900/30 disabled:opacity-50"
          >
            {loading === "restart" ? (
              <RefreshCw className="h-3 w-3 animate-spin" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" />
            )}
            Перезапустить пайплайн
          </button>
        </div>
      )}

      {(isStuck || openCBs.length > 0) && (
        <div className="rounded border border-amber-700/40 bg-amber-900/10 p-2 space-y-2">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
            <p className="text-xs font-medium text-amber-300">
              {isStuck ? "Сессия застряла" : "Circuit breaker открыт"}
            </p>
          </div>
          {stuckReason && <p className="text-[10px] text-amber-300/70">{stuckReason}</p>}
          {openCBs.length > 0 && (
            <p className="text-[10px] text-amber-300/70">Агенты: {openCBs.join(", ")}</p>
          )}
          <div className="flex flex-wrap gap-2">
            <button
              disabled={!!loading}
              onClick={() => void runRecovery("retry_agent")}
              className="flex items-center gap-1 rounded border border-amber-700/50 px-2 py-1 text-[10px] text-amber-300 hover:bg-amber-900/30 disabled:opacity-50"
            >
              <RefreshCw className="h-3 w-3" />
              Retry
            </button>
            <button
              disabled={!!loading}
              onClick={() => void runRecovery("skip_agent")}
              className="flex items-center gap-1 rounded border border-amber-700/50 px-2 py-1 text-[10px] text-amber-300 hover:bg-amber-900/30 disabled:opacity-50"
            >
              <SkipForward className="h-3 w-3" />
              Skip
            </button>
            <button
              disabled={!!loading}
              onClick={() => void handlePartialExport()}
              className="flex items-center gap-1 rounded border border-border px-2 py-1 text-[10px] text-muted-foreground hover:bg-accent disabled:opacity-50"
            >
              <Download className="h-3 w-3" />
              Partial ZIP
            </button>
          </div>
        </div>
      )}

      {specLevel === "L4" && (
        <>
          <hr className="border-border" />
          <div className="flex items-center gap-2">
            <Target className="h-3.5 w-3.5 text-pink-400" />
            <p className="text-[10px] font-semibold text-muted-foreground uppercase">
              L4 Refinement
            </p>
            {reviewCycles > 0 && (
              <span className="ml-auto rounded-full bg-pink-900/40 px-2 py-0.5 text-[10px] font-mono text-pink-300">
                Review ×{reviewCycles}
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1">
              <span className="text-[10px] text-muted-foreground">Max review</span>
              <input
                type="number"
                min={1}
                max={50}
                value={maxReviewCycles}
                disabled={!isActive}
                onChange={(e) => setMaxReviewCycles(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
              />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-muted-foreground">Confidence</span>
              <input
                type="number"
                min={0.5}
                max={1}
                step={0.05}
                value={completionConfidence}
                disabled={!isActive}
                onChange={(e) => setCompletionConfidence(Number(e.target.value))}
                className="w-full rounded border border-border bg-background px-2 py-1 text-xs"
              />
            </label>
          </div>

          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={untilConfident}
              disabled={!isActive}
              onChange={(e) => setUntilConfident(e.target.checked)}
              className="rounded border-border"
            />
            Until confident
          </label>

          {l4Criteria && (
            <p className="text-[10px] text-zinc-500">
              Критерии:{" "}
              {Object.entries(l4Criteria)
                .filter(([, v]) => !v)
                .map(([k]) => k.replace(/_/g, " "))
                .join(", ") || "все выполнены"}
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              disabled={!isActive || !!loading}
              onClick={() => void runControl()}
              className="flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
            >
              Apply settings
            </button>
            <button
              disabled={!isActive || !!loading}
              onClick={() => void runControl("replan_pipeline")}
              className={cn(
                "flex items-center gap-1.5 rounded border px-2.5 py-1.5 text-xs disabled:opacity-50",
                "border-pink-700/50 text-pink-300 hover:bg-pink-900/30"
              )}
            >
              <GitBranch className="h-3.5 w-3.5" />
              Re-plan
            </button>
            <button
              disabled={!isActive || !!loading}
              onClick={() => void runControl("retry_tasks")}
              className="flex items-center gap-1.5 rounded border border-amber-700/50 px-2.5 py-1.5 text-xs text-amber-300 hover:bg-amber-900/30 disabled:opacity-50"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Re-tasks
            </button>
          </div>
        </>
      )}
    </div>
  );
}
