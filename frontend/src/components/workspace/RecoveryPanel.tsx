import { useState } from "react";
import { AlertTriangle, SkipForward, Download, RefreshCw } from "lucide-react";
import { useSessionStore } from "@/stores/sessionStore";
import { recoverSession, exportSession } from "@/lib/api";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
}

type RecoveryAction = "retry_agent" | "skip_agent" | "force_export" | "restart_from";

const ACTIONS: { action: RecoveryAction; label: string; icon: React.ReactNode; variant: string }[] = [
  { action: "retry_agent", label: "Retry Agent", icon: <RefreshCw className="h-3.5 w-3.5" />, variant: "warn" },
  { action: "skip_agent", label: "Skip Agent", icon: <SkipForward className="h-3.5 w-3.5" />, variant: "warn" },
  { action: "force_export", label: "Force Export", icon: <Download className="h-3.5 w-3.5" />, variant: "neutral" },
];

export default function RecoveryPanel({ sessionId }: Props) {
  const { isStuck, stuckReason, currentAgent, circuitBreakers } = useSessionStore();
  const [loading, setLoading] = useState<string | null>(null);

  const openCBs = Object.keys(circuitBreakers).filter((k) => circuitBreakers[k]);
  const hasIssue = isStuck || openCBs.length > 0;

  if (!hasIssue) return null;

  const handleAction = async (action: RecoveryAction) => {
    setLoading(action);
    try {
      await recoverSession(sessionId, action, currentAgent ?? undefined);
      toast.success(`Recovery action sent: ${action}`);
    } catch (e) {
      toast.error("Recovery failed", { description: String(e) });
    } finally {
      setLoading(null);
    }
  };

  const handleExport = async () => {
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
    <div className="rounded-lg border border-amber-700/50 bg-amber-900/10 p-3 space-y-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-400" />
        <p className="text-sm font-semibold text-amber-400">
          {isStuck ? "Session Stuck" : "Circuit Breaker Open"}
        </p>
      </div>

      {stuckReason && (
        <p className="text-xs text-amber-300/70">{stuckReason}</p>
      )}

      {openCBs.length > 0 && (
        <p className="text-xs text-amber-300/70">
          Failing agents: {openCBs.join(", ")}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {ACTIONS.map(({ action, label, icon, variant }) => (
          <button
            key={action}
            disabled={!!loading}
            onClick={() => handleAction(action)}
            className={cn(
              "flex items-center gap-1.5 rounded border px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-50",
              variant === "warn"
                ? "border-amber-700 text-amber-300 hover:bg-amber-900/40"
                : "border-border text-muted-foreground hover:bg-accent"
            )}
          >
            {loading === action ? <RefreshCw className="h-3 w-3 animate-spin" /> : icon}
            {label}
          </button>
        ))}
        <button
          disabled={!!loading}
          onClick={handleExport}
          className="flex items-center gap-1.5 rounded border border-border px-2.5 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent transition-colors disabled:opacity-50"
        >
          {loading === "export" ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
          Download Partial
        </button>
      </div>
    </div>
  );
}
