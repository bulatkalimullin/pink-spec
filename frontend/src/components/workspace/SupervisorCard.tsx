import { useSessionStore } from "@/stores/sessionStore";
import { useEtaCountdown } from "@/hooks/useEtaCountdown";
import { GitBranch, Timer, CheckCircle, XCircle } from "lucide-react";
import { cn, formatDurationRu, formatEtaRu } from "@/lib/utils";

export default function SupervisorCard() {
  const supervisorRouting = useSessionStore((s) => s.supervisorRouting);
  const l4Criteria = useSessionStore((s) => s.l4Criteria);
  const specLevel = useSessionStore((s) => s.specLevel);
  const sessionProgress = useSessionStore((s) => s.sessionProgress);
  const displayEta = useEtaCountdown(
    sessionProgress?.etaSec ?? null,
    sessionProgress?.etaUpdatedAt ?? null
  );

  return (
    <div className="min-w-0 rounded-lg border border-border bg-card p-3 space-y-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Supervisor</p>

      {sessionProgress && (
        <div className="rounded border border-border/60 bg-card/50 px-2 py-1.5">
          <p className="text-[11px] text-muted-foreground">Прогноз завершения</p>
          <p className="text-xs font-medium text-foreground break-words">{formatEtaRu(displayEta)}</p>
        </div>
      )}

      {supervisorRouting && (
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <GitBranch className="h-3.5 w-3.5 text-pink-400 flex-shrink-0" />
            <span className="text-xs font-medium text-foreground min-w-0 break-words">
              → <span className="text-primary font-mono break-all">{supervisorRouting.next_agent}</span>
            </span>
          </div>
          <p className="text-xs text-muted-foreground pl-5 break-words">{supervisorRouting.reason}</p>
          {supervisorRouting.remaining_sec != null && (
            <div className="flex items-center gap-1.5 pl-5">
              <Timer className="h-3 w-3 text-zinc-500 flex-shrink-0" />
              <span className="text-[11px] text-zinc-500">
                Лимит: {formatDurationRu(supervisorRouting.remaining_sec)}
              </span>
            </div>
          )}
        </div>
      )}

      {specLevel === "L4" && l4Criteria && (
        <div className="min-w-0">
          <p className="text-[11px] text-muted-foreground mb-1.5 font-medium">L4 Completion Criteria</p>
          <div className="space-y-0.5">
            {Object.entries(l4Criteria).map(([key, met]) => (
              <div key={key} className="flex items-start gap-2 min-w-0">
                {met ? (
                  <CheckCircle className="h-3 w-3 text-emerald-400 flex-shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="h-3 w-3 text-zinc-600 flex-shrink-0 mt-0.5" />
                )}
                <span
                  className={cn(
                    "text-[11px] break-words min-w-0",
                    met ? "text-emerald-400" : "text-zinc-500"
                  )}
                >
                  {key.replace(/_/g, " ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!supervisorRouting && !l4Criteria && !sessionProgress && (
        <p className="text-xs text-zinc-600">Ожидаем первое решение супервизора…</p>
      )}
    </div>
  );
}
