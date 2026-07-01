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
