import { create } from "zustand";

export interface LogEntry {
  seq: number;
  type: string;
  ts: string;
  session_id: string;
  payload: Record<string, unknown>;
}

export interface SystemMetrics {
  cpu_percent: number;
  ram_percent: number;
  ram_used_mb: number;
  ram_total_mb: number;
  swap_percent: number;
  disk_percent: number;
  process_rss_mb: number;
  gpu?: {
    name: string;
    util_percent: number;
    mem_used_mb: number;
    mem_total_mb: number;
    temp_c: number;
    driver_version?: string | null;
  } | null;
  ts?: string;
}

export interface SessionProgress {
  percent: number;
  label: string;
  detail: string | null;
  stepIndex: number;
  totalSteps: number;
  elapsedSec: number;
  etaSec: number | null;
  etaUpdatedAt: number;
  stageId: string;
}

export interface AgentState {
  id: string;
  name: string;
  status: "pending" | "running" | "success" | "failed" | "degraded" | "skipped" | "cancelled";
  startedAt?: string;
  completedAt?: string;
  durationMs?: number;
  passNumber: number;
}

export interface Assumption {
  text: string;
  agentId: string;
  ts: string;
}

export interface FallbackEvent {
  layer: string;
  step: string;
  message: string;
  from?: string;
  to?: string;
  ts: string;
}

export interface PipelineStep {
  id: string;
  name: string;
  executor?: string;
  artifact_key?: string | null;
  required?: boolean;
  prompt_focus?: string | null;
  target_count?: number | null;
}

const LEGACY_PIPELINE: PipelineStep[] = [
  { id: "researcher", name: "Researcher" },
  { id: "pipeline_planner", name: "Pipeline Planner" },
  { id: "product_analyst", name: "Product Specification" },
  { id: "architect", name: "Architecture" },
  { id: "api_designer", name: "API Design" },
  { id: "ui_designer", name: "UI Design" },
  { id: "context_manager", name: "Context Manager" },
  { id: "task_decomposer", name: "Task Decomposition" },
  { id: "reviewer", name: "Reviewer" },
  { id: "export", name: "Export" },
];

interface SessionStore {
  sessionId: string | null;
  sessionStatus: string;
  specLevel: string;
  idea: string;
  wsStatus: "disconnected" | "connecting" | "connected" | "reconnecting" | "error";

  // Feed
  logs: LogEntry[];
  unreadCount: number;
  metricsHistory: SystemMetrics[];

  // Agents
  agents: Record<string, AgentState>;

  // Transparency
  assumptions: Assumption[];
  fallbacks: FallbackEvent[];
  currentAgent: string | null;
  supervisorRouting: { next_agent: string; reason: string; remaining_sec?: number } | null;
  l4Criteria: Record<string, boolean> | null;
  sessionProgress: SessionProgress | null;
  reviewCycles: number;

  // Recovery
  isStuck: boolean;
  stuckReason: string | null;
  lastEventAt: number;
  circuitBreakers: Record<string, boolean>;
  intakeSummary: string | null;

  // Dynamic pipeline
  pipeline: PipelineStep[];
  pipelineReasoning: string;

  // Actions
  setSessionId: (id: string, level: string, idea: string, status?: string) => void;
  setPipeline: (steps: PipelineStep[], reasoning?: string) => void;
  setWsStatus: (s: SessionStore["wsStatus"]) => void;
  pushLog: (entry: LogEntry) => void;
  replaceLogs: (entries: LogEntry[]) => void;
  pushMetrics: (m: SystemMetrics) => void;
  markRead: () => void;
  handleEnvelope: (envelope: LogEntry) => void;
  reset: () => void;
}

const NON_FEED_TYPES = new Set(["session_snapshot", "ping", "pong"]);

const AGENT_STATUS_VALUES = new Set<AgentState["status"]>([
  "pending",
  "running",
  "success",
  "failed",
  "degraded",
  "skipped",
  "cancelled",
]);

function normalizeAgentStatus(raw: string): AgentState["status"] {
  if (AGENT_STATUS_VALUES.has(raw as AgentState["status"])) {
    return raw as AgentState["status"];
  }
  if (raw === "timeout") return "failed";
  return "degraded";
}

const AGENT_NAMES: Record<string, string> = {
  researcher: "Researcher",
  product_analyst: "Product Analyst",
  architect: "Architect",
  api_designer: "API Designer",
  ui_designer: "UI Designer",
  task_decomposer: "Task Decomposer",
  reviewer: "Reviewer",
  context_manager: "Context Manager",
  supervisor: "Supervisor",
  pipeline_planner: "Pipeline Planner",
  intake: "Intake",
  export: "Export",
};

const MAX_LOGS = 5000;
const MAX_METRICS = 300;

export const useSessionStore = create<SessionStore>((set, get) => ({
  sessionId: null,
  sessionStatus: "pending",
  specLevel: "L2",
  idea: "",
  wsStatus: "disconnected",
  logs: [],
  unreadCount: 0,
  metricsHistory: [],
  agents: {},
  assumptions: [],
  fallbacks: [],
  currentAgent: null,
  supervisorRouting: null,
  l4Criteria: null,
  sessionProgress: null,
  reviewCycles: 0,
  isStuck: false,
  stuckReason: null,
  lastEventAt: Date.now(),
  circuitBreakers: {},
  intakeSummary: null,
  pipeline: LEGACY_PIPELINE,
  pipelineReasoning: "",

  setSessionId: (id, level, idea, status = "running") =>
    set({ sessionId: id, specLevel: level, idea, sessionStatus: status }),

  setPipeline: (steps, reasoning = "") =>
    set({
      pipeline: [...steps, { id: "export", name: "Export" }],
      pipelineReasoning: reasoning,
    }),

  setWsStatus: (s) => set({ wsStatus: s }),

  pushLog: (entry) =>
    set((state) => {
      const logs = [...state.logs, entry].slice(-MAX_LOGS);
      const isWarnOrError = ["warn", "error"].includes(entry.payload?.level as string);
      const isCriticalType = ["session_stuck", "agent_timeout", "circuit_breaker_open", "error"].includes(entry.type);
      return {
        logs,
        unreadCount: state.unreadCount + (isWarnOrError || isCriticalType ? 1 : 0),
      };
    }),

  replaceLogs: (entries) =>
    set((state) => {
      const bySeq = new Map<number, LogEntry>();
      for (const e of state.logs) bySeq.set(e.seq, e);
      for (const e of entries) {
        bySeq.set(e.seq, {
          seq: e.seq,
          type: e.type,
          ts: e.ts,
          session_id: e.session_id ?? state.sessionId ?? "",
          payload: e.payload ?? {},
        });
      }
      const logs = [...bySeq.values()].sort((a, b) => a.seq - b.seq).slice(-MAX_LOGS);
      return { logs };
    }),

  pushMetrics: (m) =>
    set((state) => ({
      metricsHistory: [...state.metricsHistory, m].slice(-MAX_METRICS),
    })),

  markRead: () => set({ unreadCount: 0 }),

  handleEnvelope: (envelope) => {
    const { type, payload, ts } = envelope;
    const state = get();

    set({ lastEventAt: Date.now() });

    // Push to log feed (skip high-level control frames and metrics)
    if (type !== "system_metrics" && !NON_FEED_TYPES.has(type)) {
      get().pushLog(envelope);
    }

    switch (type) {
      case "system_metrics":
        get().pushMetrics({ ...(payload as unknown as SystemMetrics), ts });
        break;

      case "agent_started": {
        const p = payload as { agent_id: string; agent_name: string; pass_number: number };
        set((s) => ({
          currentAgent: p.agent_id,
          isStuck: false,
          stuckReason: null,
          agents: {
            ...s.agents,
            [p.agent_id]: {
              id: p.agent_id,
              name: p.agent_name || AGENT_NAMES[p.agent_id] || p.agent_id,
              status: "running",
              startedAt: ts,
              passNumber: p.pass_number,
            },
          },
        }));
        break;
      }

      case "agent_completed": {
        const p = payload as { agent_id: string; status: string; duration_ms: number };
        set((s) => ({
          agents: {
            ...s.agents,
            [p.agent_id]: {
              ...(s.agents[p.agent_id] ?? {
                id: p.agent_id,
                name: s.agents[p.agent_id]?.name || AGENT_NAMES[p.agent_id] || p.agent_id,
                passNumber: 1,
              }),
              status: normalizeAgentStatus(p.status),
              completedAt: ts,
              durationMs: p.duration_ms,
            },
          },
          currentAgent: state.currentAgent === p.agent_id ? null : state.currentAgent,
        }));
        break;
      }

      case "stage_changed": {
        const p = payload as {
          stage_id: string;
          label: string;
          detail?: string | null;
          percent: number;
          step_index: number;
          total_steps: number;
          elapsed_sec: number;
          eta_sec?: number | null;
        };
        set({
          sessionProgress: {
            stageId: p.stage_id,
            label: p.label,
            detail: p.detail ?? null,
            percent: p.percent,
            stepIndex: p.step_index,
            totalSteps: p.total_steps,
            elapsedSec: p.elapsed_sec,
            etaSec: p.eta_sec ?? null,
            etaUpdatedAt: Date.now(),
          },
        });
        break;
      }

      case "saturation_progress": {
        const p = payload as { iteration: number; chunks: number };
        set((s) => {
          if (!s.sessionProgress) return {};
          return {
            sessionProgress: {
              ...s.sessionProgress,
              detail: `Итерация ${p.iteration} · ${p.chunks} фрагментов`,
            },
          };
        });
        break;
      }

      case "supervisor_routing": {
        const p = payload as { next_agent: string; reason: string; remaining_sec?: number };
        set({ supervisorRouting: p });
        break;
      }

      case "assumption_logged": {
        const p = payload as { text: string; agent_id: string };
        set((s) => ({
          assumptions: [...s.assumptions, { text: p.text, agentId: p.agent_id, ts }],
        }));
        break;
      }

      case "artifact_patched": {
        const p = payload as {
          artifact_type: string;
          mode: string;
          patches_applied?: number;
          lines_added?: number;
          lines_removed?: number;
        };
        const modeLabel =
          p.mode === "patch"
            ? `Patched ${p.artifact_type}: +${p.lines_added ?? 0}/-${p.lines_removed ?? 0} lines`
            : p.mode === "generate"
              ? `Generated ${p.artifact_type}`
              : `Unchanged ${p.artifact_type}`;
        get().pushLog({
          seq: envelope.seq,
          type: "artifact_patched",
          ts: ts ?? new Date().toISOString(),
          session_id: envelope.session_id,
          payload: { ...p, message: modeLabel },
        });
        break;
      }

      case "fallback_triggered": {
        const p = payload as { layer: string; step: string; message: string; from?: string; to?: string };
        set((s) => ({
          fallbacks: [...s.fallbacks, { ...p, ts }],
        }));
        break;
      }

      case "session_stuck": {
        const p = payload as { reason: string };
        set({ isStuck: true, stuckReason: p.reason });
        break;
      }

      case "recovery_started":
        break;

      case "circuit_breaker_open": {
        const p = payload as { agent_id: string };
        set((s) => ({ circuitBreakers: { ...s.circuitBreakers, [p.agent_id]: true } }));
        break;
      }

      case "circuit_breaker_closed": {
        const p = payload as { agent_id: string };
        set((s) => {
          const cbs = { ...s.circuitBreakers };
          delete cbs[p.agent_id];
          return { circuitBreakers: cbs };
        });
        break;
      }

      case "completion_check": {
        const p = payload as { criteria: Record<string, boolean> };
        set({ l4Criteria: p.criteria });
        break;
      }

      case "session_completed_partial": {
        const p = payload as {
          failed_criteria?: string[];
          criteria?: Record<string, boolean>;
        };
        if (p.criteria) {
          set({ l4Criteria: p.criteria });
        }
        break;
      }

      case "refinement_cycle": {
        const p = payload as { cycle: number };
        set({ reviewCycles: p.cycle });
        break;
      }

      case "intake_started": {
        const p = payload as { summary?: string; questions_count?: number };
        set({
          sessionStatus: "waiting_user",
          intakeSummary: p.summary ?? null,
        });
        break;
      }

      case "intake_waiting": {
        set({ sessionStatus: "waiting_user" });
        break;
      }

      case "intake_complete": {
        set({ sessionStatus: "running", intakeSummary: null });
        break;
      }

      case "question_asked":
        break;

      case "refinement_settings": {
        break;
      }

      case "pipeline_planned": {
        const p = payload as { steps: PipelineStep[]; reasoning?: string };
        if (p.steps?.length) {
          get().setPipeline(p.steps, p.reasoning ?? "");
        }
        break;
      }

      case "done": {
        const p = payload as { is_partial?: boolean };
        set({
          sessionStatus: p.is_partial ? "completed_partial" : "completed",
          currentAgent: null,
          isStuck: false,
          sessionProgress: null,
        });
        break;
      }

      case "session_snapshot": {
        const p = payload as { status: string; log_tail?: LogEntry[] };
        set({ sessionStatus: p.status });
        if (p.log_tail) {
          p.log_tail.forEach((e) =>
            get().pushLog({
              seq: e.seq,
              type: e.type,
              ts: e.ts ?? ts ?? new Date().toISOString(),
              session_id: envelope.session_id,
              payload: e.payload ?? {},
            })
          );
        }
        break;
      }
    }
  },

  reset: () =>
    set({
      sessionId: null,
      sessionStatus: "pending",
      specLevel: "L2",
      idea: "",
      wsStatus: "disconnected",
      logs: [],
      unreadCount: 0,
      metricsHistory: [],
      agents: {},
      assumptions: [],
      fallbacks: [],
      currentAgent: null,
      supervisorRouting: null,
      l4Criteria: null,
      sessionProgress: null,
      reviewCycles: 0,
      isStuck: false,
      stuckReason: null,
      lastEventAt: Date.now(),
      circuitBreakers: {},
      intakeSummary: null,
      pipeline: LEGACY_PIPELINE,
      pipelineReasoning: "",
    }),
}));
