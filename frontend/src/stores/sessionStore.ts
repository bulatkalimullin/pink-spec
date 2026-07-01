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
    util_percent: number;
    mem_used_mb: number;
    mem_total_mb: number;
    temp_c: number;
  } | null;
  ts?: string;
}

export interface AgentState {
  id: string;
  name: string;
  status: "pending" | "running" | "success" | "failed" | "degraded";
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

  // Recovery
  isStuck: boolean;
  stuckReason: string | null;
  circuitBreakers: Record<string, boolean>;

  // Dynamic pipeline
  pipeline: PipelineStep[];
  pipelineReasoning: string;

  // Actions
  setSessionId: (id: string, level: string, idea: string) => void;
  setPipeline: (steps: PipelineStep[], reasoning?: string) => void;
  setWsStatus: (s: SessionStore["wsStatus"]) => void;
  pushLog: (entry: LogEntry) => void;
  pushMetrics: (m: SystemMetrics) => void;
  markRead: () => void;
  handleEnvelope: (envelope: LogEntry) => void;
  reset: () => void;
}

const NON_FEED_TYPES = new Set(["session_snapshot", "ping", "pong"]);

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
  isStuck: false,
  stuckReason: null,
  circuitBreakers: {},
  pipeline: LEGACY_PIPELINE,
  pipelineReasoning: "",

  setSessionId: (id, level, idea) =>
    set({ sessionId: id, specLevel: level, idea, sessionStatus: "running" }),

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

  pushMetrics: (m) =>
    set((state) => ({
      metricsHistory: [...state.metricsHistory, m].slice(-MAX_METRICS),
    })),

  markRead: () => set({ unreadCount: 0 }),

  handleEnvelope: (envelope) => {
    const { type, payload, ts } = envelope;
    const state = get();

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
              status: p.status as AgentState["status"],
              completedAt: ts,
              durationMs: p.duration_ms,
            },
          },
          currentAgent: state.currentAgent === p.agent_id ? null : state.currentAgent,
        }));
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
        set({ isStuck: false, stuckReason: null });
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

      case "pipeline_planned": {
        const p = payload as { steps: PipelineStep[]; reasoning?: string };
        if (p.steps?.length) {
          get().setPipeline(p.steps, p.reasoning ?? "");
        }
        break;
      }

      case "done":
        set({ sessionStatus: "completed", currentAgent: null, isStuck: false });
        break;

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
      isStuck: false,
      stuckReason: null,
      circuitBreakers: {},
      pipeline: LEGACY_PIPELINE,
      pipelineReasoning: "",
    }),
}));
