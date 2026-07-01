import { cn } from "@/lib/utils";
import { useSessionStore, AgentState } from "@/stores/sessionStore";
import { CheckCircle, Circle, Loader2, XCircle, AlertTriangle } from "lucide-react";

const STATUS_CONFIG: Record<AgentState["status"], { icon: React.ReactNode; color: string; label: string }> = {
  pending: { icon: <Circle className="h-3.5 w-3.5" />, color: "text-zinc-600", label: "Pending" },
  running: {
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin" />,
    color: "text-emerald-400",
    label: "Running",
  },
  success: { icon: <CheckCircle className="h-3.5 w-3.5" />, color: "text-pink-400", label: "Done" },
  failed: { icon: <XCircle className="h-3.5 w-3.5" />, color: "text-red-400", label: "Failed" },
  degraded: { icon: <AlertTriangle className="h-3.5 w-3.5" />, color: "text-orange-400", label: "Degraded" },
};

export default function AgentTimeline() {
  const agents = useSessionStore((s) => s.agents);
  const currentAgent = useSessionStore((s) => s.currentAgent);
  const pipeline = useSessionStore((s) => s.pipeline);
  const pipelineReasoning = useSessionStore((s) => s.pipelineReasoning);

  const steps = pipeline.length > 0 ? pipeline : [];

  return (
    <div className="flex flex-col gap-0.5 p-3">
      <p className="mb-2 text-xs font-medium text-muted-foreground">Agent Timeline</p>
      {pipelineReasoning && (
        <p className="mb-2 rounded border border-border bg-card/50 px-2 py-1.5 text-[10px] text-muted-foreground leading-snug">
          {pipelineReasoning}
        </p>
      )}
      {steps.map((step, i) => {
        const agentId = step.id;
        const agent = agents[agentId];
        const isCurrent = currentAgent === agentId;
        const status = agent?.status ?? "pending";
        const config = STATUS_CONFIG[status];
        const label = agent?.name || step.name || agentId;
        const isTaskBatch =
          step.executor === "builtin:task_decomposer" || step.id.startsWith("tasks_");
        const batchHint = isTaskBatch && step.prompt_focus
          ? step.prompt_focus.slice(0, 40)
          : null;

        return (
          <div key={`${agentId}-${i}`} className="flex items-start gap-2">
            <div className="flex flex-col items-center">
              <div className={cn("flex-shrink-0 mt-0.5", config.color)}>{config.icon}</div>
              {i < steps.length - 1 && (
                <div
                  className={cn(
                    "w-px flex-1 my-0.5",
                    status === "success" ? "bg-pink-800/60" : "bg-border"
                  )}
                  style={{ minHeight: 14 }}
                />
              )}
            </div>

            <div
              className={cn(
                "flex-1 rounded px-2 py-1 text-xs transition-all min-w-0",
                isCurrent && "bg-emerald-900/25 border border-emerald-700/50",
                !isCurrent && status === "success" && "bg-pink-900/15 border border-pink-800/30",
                !isCurrent && status === "failed" && "bg-red-900/15 border border-red-800/30",
                !isCurrent && status === "pending" && "border border-transparent"
              )}
            >
              <div className="flex items-center gap-2">
                <span className={cn("font-medium truncate", isCurrent ? "text-emerald-300" : config.color)}>
                  {label}
                </span>
                {agent?.passNumber && agent.passNumber > 1 && (
                  <span className="text-[10px] text-muted-foreground">×{agent.passNumber}</span>
                )}
                <div className="flex-1" />
                {agent?.durationMs && (
                  <span className="text-[10px] text-zinc-600 shrink-0">{agent.durationMs}ms</span>
                )}
              </div>
              {batchHint && (
                <p className="mt-0.5 text-[10px] text-zinc-500 truncate" title={step.prompt_focus ?? ""}>
                  {batchHint}…
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
