import { useSessionStore } from "@/stores/sessionStore";
import { GitBranch, Timer, CheckCircle, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { formatDuration } from "@/lib/utils";

export default function SupervisorCard() {
  const supervisorRouting = useSessionStore((s) => s.supervisorRouting);
  const l4Criteria = useSessionStore((s) => s.l4Criteria);
  const specLevel = useSessionStore((s) => s.specLevel);

  return (
    <div className="rounded-lg border border-border bg-card p-3 space-y-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Supervisor</p>

      {supervisorRouting && (
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <GitBranch className="h-3.5 w-3.5 text-pink-400" />
            <span className="text-xs font-medium text-foreground">
              → <span className="text-primary font-mono">{supervisorRouting.next_agent}</span>
            </span>
          </div>
          <p className="text-xs text-muted-foreground pl-5">{supervisorRouting.reason}</p>
          {supervisorRouting.remaining_sec != null && (
            <div className="flex items-center gap-1.5 pl-5">
              <Timer className="h-3 w-3 text-zinc-500" />
              <span className="text-[11px] text-zinc-500">
                {formatDuration(supervisorRouting.remaining_sec)} remaining
              </span>
            </div>
          )}
        </div>
      )}

      {specLevel === "L4" && l4Criteria && (
        <div>
          <p className="text-[11px] text-muted-foreground mb-1.5 font-medium">L4 Completion Criteria</p>
          <div className="space-y-0.5">
            {Object.entries(l4Criteria).map(([key, met]) => (
              <div key={key} className="flex items-center gap-2">
                {met ? (
                  <CheckCircle className="h-3 w-3 text-emerald-400 flex-shrink-0" />
                ) : (
                  <XCircle className="h-3 w-3 text-zinc-600 flex-shrink-0" />
                )}
                <span className={cn("text-[11px]", met ? "text-emerald-400" : "text-zinc-500")}>
                  {key.replace(/_/g, " ")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!supervisorRouting && !l4Criteria && (
        <p className="text-xs text-zinc-600">Waiting for first routing decision…</p>
      )}
    </div>
  );
}
