import * as Progress from "@radix-ui/react-progress";
import { useSessionStore } from "@/stores/sessionStore";
import { useEtaCountdown } from "@/hooks/useEtaCountdown";
import { cn, formatDurationRu, formatEtaRu } from "@/lib/utils";

export default function SessionProgressBar() {
  const sessionStatus = useSessionStore((s) => s.sessionStatus);
  const progress = useSessionStore((s) => s.sessionProgress);

  const displayEta = useEtaCountdown(progress?.etaSec ?? null, progress?.etaUpdatedAt ?? null);

  if (sessionStatus !== "running" || !progress) {
    return null;
  }

  return (
    <div className="border-b border-border bg-card/60 px-3 py-2 sm:px-4">
      <div className="flex items-start justify-between gap-3 min-w-0">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-foreground truncate">{progress.label}</p>
          {progress.detail && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">{progress.detail}</p>
          )}
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-mono font-medium text-primary">{progress.percent}%</p>
          <p className="text-[11px] text-muted-foreground whitespace-nowrap">
            {formatEtaRu(displayEta)}
          </p>
        </div>
      </div>

      <Progress.Root
        value={progress.percent}
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800"
      >
        <Progress.Indicator
          className={cn("h-full rounded-full bg-pink-500 transition-all duration-500")}
          style={{ width: `${progress.percent}%` }}
        />
      </Progress.Root>

      <p className="mt-1.5 text-[10px] text-zinc-500">
        Шаг {progress.stepIndex}/{progress.totalSteps}
        {" · "}
        прошло {formatDurationRu(progress.elapsedSec)}
      </p>
    </div>
  );
}
