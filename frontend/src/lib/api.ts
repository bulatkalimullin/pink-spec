const BASE = "/api/v1";

export async function createAndStartSession(idea: string, rules: object): Promise<string> {
  const create = await fetch(`${BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea, rules }),
  });
  if (!create.ok) throw new Error(`Create failed: ${create.statusText}`);
  const { session_id } = await create.json();

  const start = await fetch(`${BASE}/sessions/${session_id}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea, rules }),
  });
  if (!start.ok) throw new Error(`Start failed: ${start.statusText}`);

  return session_id;
}

export async function getSession(sessionId: string) {
  const r = await fetch(`${BASE}/sessions/${sessionId}`);
  if (!r.ok) throw new Error("Session not found");
  return r.json();
}

export async function getSessionHealth(sessionId: string) {
  const r = await fetch(`${BASE}/sessions/${sessionId}/health`);
  return r.json();
}

export async function getSpecLevels() {
  const r = await fetch(`${BASE}/spec-levels`);
  return r.json();
}

export async function getRulesSchema() {
  const r = await fetch(`${BASE}/schema/rules`);
  return r.json();
}

export async function submitAnswer(sessionId: string, questionId: string, answer: unknown) {
  return fetch(`${BASE}/sessions/${sessionId}/answers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: questionId, answer }),
  });
}

export async function recoverSession(sessionId: string, action: string, targetAgent?: string) {
  return fetch(`${BASE}/sessions/${sessionId}/recover`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, target_agent: targetAgent }),
  });
}

export interface SessionControlPayload {
  max_review_cycles?: number;
  completion_confidence?: number;
  until_confident?: boolean;
  action?: string;
}

export async function getSessionControl(sessionId: string) {
  const r = await fetch(`${BASE}/sessions/${sessionId}/control`);
  if (!r.ok) throw new Error("Failed to load control settings");
  return r.json() as Promise<{
    max_review_cycles: number;
    completion_confidence: number;
    until_confident: boolean;
    overrides_active: boolean;
  }>;
}

export async function sendSessionControl(sessionId: string, payload: SessionControlPayload) {
  const r = await fetch(`${BASE}/sessions/${sessionId}/control`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error("Control request failed");
  return r.json();
}

export async function exportSession(sessionId: string): Promise<Blob> {
  const r = await fetch(`${BASE}/sessions/${sessionId}/export`);
  if (!r.ok) throw new Error("Export failed");
  return r.blob();
}

export async function getSystemMetrics() {
  const r = await fetch(`${BASE}/system/metrics`);
  return r.json();
}

export async function getArtifact(sessionId: string, artifactType: string): Promise<string> {
  const r = await fetch(`${BASE}/sessions/${sessionId}/artifacts/${artifactType}`);
  if (!r.ok) throw new Error(`Artifact not found: ${artifactType}`);
  return r.text();
}

export async function getTaskContent(sessionId: string, path: string): Promise<string> {
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  const r = await fetch(`${BASE}/sessions/${sessionId}/artifacts/tasks/${encoded}`);
  if (!r.ok) throw new Error(`Task not found: ${path}`);
  return r.text();
}

export async function getSessionTasks(sessionId: string) {
  const r = await fetch(`${BASE}/sessions/${sessionId}/tasks`);
  if (!r.ok) throw new Error("Failed to load tasks");
  return r.json() as Promise<{ tasks: { path: string; name: string }[] }>;
}

export async function getSessionLogs(sessionId: string, fromSeq = 0, limit = 500) {
  const r = await fetch(
    `${BASE}/sessions/${sessionId}/logs?from_seq=${fromSeq}&limit=${limit}`
  );
  if (!r.ok) throw new Error("Failed to load logs");
  return r.json() as Promise<{ logs: unknown[]; count: number }>;
}

export interface SessionMetricsSummary {
  session_id: string;
  status: string;
  spec_level: string;
  completed_at: string;
  duration_sec: number;
  quality_score: number;
  artifacts_count: number;
  tasks_total: number;
  errors_count: number;
  efficiency_score: number;
  reliability_score: number;
}

export interface GlobalStats {
  updated_at: string;
  totals: {
    sessions: number;
    completed: number;
    partial: number;
    failed: number;
    artifacts: number;
    tasks: number;
    errors: number;
    fallbacks: number;
  };
  rates: {
    success_rate: number;
    partial_rate: number;
    avg_quality_score: number;
    avg_efficiency_score: number;
    avg_reliability_score: number;
  };
  by_spec_level: Record<
    string,
    { count: number; completed: number; avg_duration_sec: number; avg_tasks: number; avg_quality: number }
  >;
  agent_leaderboard: {
    agent_id: string;
    total_calls: number;
    avg_duration_ms: number;
    failure_rate_pct: number;
    failures: number;
  }[];
  trends: {
    sessions_by_day: { date: string; count: number }[];
    avg_duration_by_day: { date: string; avg_duration_sec: number }[];
  };
  reliability: {
    circuit_breaker_opens: number;
    agent_timeouts: number;
    session_stuck_events: number;
    budget_warnings: number;
    stuck_sessions: number;
  };
  infrastructure: {
    avg_cpu_peak: number;
    avg_ram_peak: number;
    avg_gpu_mem_peak: number;
  };
  recent_sessions: SessionMetricsSummary[];
}

export async function getGlobalStats(): Promise<GlobalStats> {
  const r = await fetch(`${BASE}/stats/global`);
  if (!r.ok) throw new Error("Failed to load global stats");
  return r.json();
}

export async function getSessionMetricsList(params?: {
  limit?: number;
  offset?: number;
  spec_level?: string;
}) {
  const q = new URLSearchParams();
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  if (params?.spec_level) q.set("spec_level", params.spec_level);
  const r = await fetch(`${BASE}/stats/sessions?${q}`);
  if (!r.ok) throw new Error("Failed to load session metrics");
  return r.json() as Promise<{
    sessions: SessionMetricsSummary[];
    total: number;
    limit: number;
    offset: number;
  }>;
}

export async function rebuildStats(force = false) {
  const r = await fetch(`${BASE}/stats/rebuild?force=${force}`, { method: "POST" });
  if (!r.ok) throw new Error("Rebuild failed");
  return r.json() as Promise<{ processed: number; skipped: number; errors: number; message: string }>;
}
