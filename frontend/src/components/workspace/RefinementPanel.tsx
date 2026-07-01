import { useEffect, useState } from "react";
import { GitBranch, RefreshCw, RotateCcw, Settings2, Target } from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";
import { getSessionControl, sendSessionControl } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
}

export default function RefinementPanel({ sessionId }: Props) {
  const { specLevel, sessionStatus, reviewCycles, l4Criteria } = useSessionStore();
  const [maxReviewCycles, setMaxReviewCycles] = useState(10);
  const [completionConfidence, setCompletionConfidence] = useState(0.85);
  const [untilConfident, setUntilConfident] = useState(true);
  const [loading, setLoading] = useState<string | null>(null);

  const isActive = sessionStatus === "running" || sessionStatus === "degraded";

  useEffect(() => {
    if (!sessionId || specLevel !== "L4") return;
    getSessionControl(sessionId)
      .then((cfg) => {
        setMaxReviewCycles(cfg.max_review_cycles);
        setCompletionConfidence(cfg.completion_confidence);
        setUntilConfident(cfg.until_confident);
      })
      .catch(() => {});
  }, [sessionId, specLevel]);

  const applySettings = async (action?: string) => {
    setLoading(action ?? "settings");
    try {
      await sendSessionControl(sessionId, {
        max_review_cycles: maxReviewCycles,
        completion_confidence: completionConfidence,
        until_confident: untilConfident,
        action,
      });
      toast.success(action ? `Action sent: ${action}` : "Refinement settings applied");
    } catch (e) {
      toast.error("Failed to update refinement settings", { description: String(e) });
    } finally {
      setLoading(null);
    }
  };

  if (specLevel !== "L4") return null;

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-3">
      <div className="flex items-center gap-2">
        <Settings2 className="h-4 w-4 text-pink-400" />
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
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
          <span className="text-[10px] text-muted-foreground">Max review attempts</span>
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
          <span className="text-[10px] text-muted-foreground">Min confidence</span>
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
        Until reviewer is confident (don&apos;t export early)
      </label>

      {l4Criteria && (
        <p className="text-[10px] text-zinc-500">
          Criteria:{" "}
          {Object.entries(l4Criteria)
            .filter(([, v]) => !v)
            .map(([k]) => k.replace(/_/g, " "))
            .join(", ") || "all met"}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          disabled={!isActive || !!loading}
          onClick={() => void applySettings()}
          className="flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
        >
          {loading === "settings" ? (
            <RefreshCw className="h-3 w-3 animate-spin" />
          ) : (
            <Target className="h-3.5 w-3.5" />
          )}
          Apply settings
        </button>
        <button
          disabled={!isActive || !!loading}
          onClick={() => void applySettings("replan_pipeline")}
          className={cn(
            "flex items-center gap-1.5 rounded border px-2.5 py-1.5 text-xs disabled:opacity-50",
            "border-pink-700/50 text-pink-300 hover:bg-pink-900/30"
          )}
        >
          {loading === "replan_pipeline" ? (
            <RefreshCw className="h-3 w-3 animate-spin" />
          ) : (
            <GitBranch className="h-3.5 w-3.5" />
          )}
          Re-run Planner
        </button>
        <button
          disabled={!isActive || !!loading}
          onClick={() => void applySettings("retry_tasks")}
          className="flex items-center gap-1.5 rounded border border-amber-700/50 px-2.5 py-1.5 text-xs text-amber-300 hover:bg-amber-900/30 disabled:opacity-50"
        >
          {loading === "retry_tasks" ? (
            <RefreshCw className="h-3 w-3 animate-spin" />
          ) : (
            <RotateCcw className="h-3.5 w-3.5" />
          )}
          Re-run Tasks
        </button>
      </div>
    </div>
  );
}
