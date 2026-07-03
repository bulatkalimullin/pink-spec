import type { AgentState, LogEntry } from "@/stores/sessionStore";

/** Human-readable line for one event (used in Activity feed + clipboard). */
export function formatLogMessage(entry: LogEntry): string {
  const p = entry.payload;
  switch (entry.type) {
    case "log_entry":
      return (p?.message as string) ?? "";
    case "supervisor_routing":
      return `Route → ${p?.next_agent} — ${p?.reason}`;
    case "agent_started":
      return `${p?.agent_name ?? p?.agent_id} started (pass #${p?.pass_number})`;
    case "agent_completed":
      return `${p?.agent_id} completed in ${p?.duration_ms}ms — ${p?.status}`;
    case "token_delta":
      return `[${p?.agent_id}] +${(p?.delta as string)?.length ?? 0} chars`;
    case "fallback_triggered":
      return `[${p?.layer}] ${p?.message}`;
    case "assumption_logged":
      return `[${p?.agent_id}] ${p?.text}`;
    case "question_asked":
      return `Question (${p?.priority}): ${p?.text}`;
    case "intake_started":
      return `Intake: ${p?.questions_count ?? 0} questions — ${p?.summary ?? ""}`;
    case "intake_waiting":
      return `Intake waiting: ${p?.questions_count ?? 0} questions`;
    case "intake_complete":
      return `Intake complete (ready=${p?.ready}, answers=${p?.answers_count ?? 0})`;
    case "session_stuck":
      return `Stuck: ${p?.reason} (${p?.since_sec}s)`;
    case "agent_timeout":
      return `${p?.agent_id} timed out after ${p?.timeout_sec}s`;
    case "circuit_breaker_open":
      return `Circuit breaker OPEN for ${p?.agent_id}`;
    case "circuit_breaker_closed":
      return `Circuit breaker CLOSED for ${p?.agent_id}`;
    case "recovery_started":
      return `Recovery: ${p?.action} on ${p?.target_agent ?? "session"}`;
    case "checkpoint_saved":
      return `Checkpoint: ${p?.checkpoint_id} (${p?.agent_id})`;
    case "artifact_preview":
      return `${p?.artifact_type} preview`;
    case "artifact_patched":
      return (p?.message as string) ?? `${p?.artifact_type} ${p?.mode}`;
    case "stage_changed": {
      const detail = p?.detail ? ` — ${p.detail}` : "";
      return `${p?.label}${detail} (${p?.percent}%)`;
    }
    case "saturation_progress":
      return `RAG iteration ${p?.iteration}, ${p?.chunks} chunks, novelty=${p?.novelty}`;
    case "summary_updated":
      return `Summary [${p?.level}]: ${(p?.preview as string)?.slice(0, 80) ?? ""}`;
    case "pipeline_planned":
      return `Pipeline planned: ${(p?.steps as unknown[])?.length ?? 0} steps`;
    case "completion_check":
      return `Completion check: all_met=${p?.all_met}`;
    case "session_completed_partial":
      return `Partial complete: ${(p?.failed_criteria as string[])?.join(", ") ?? "criteria unmet"}`;
    case "budget_warning":
      return `Budget warning: ${p?.remaining_sec}s left (${p?.mode})`;
    case "task_batch_generated":
      return `Tasks batch [${p?.phase}]: +${p?.count}`;
    case "refinement_settings":
      return `Refinement settings updated`;
    case "refinement_cycle":
      return `Review cycle #${p?.cycle}`;
    case "error":
      return `Error [${p?.code}]: ${p?.message}`;
    case "done":
      return `Complete! ${p?.artifacts_count} artifacts, ${p?.duration_sec}s`;
    case "worker.session_claimed":
      return `Worker claimed session (${p?.worker})`;
    case "system_warning":
      return `System ${p?.metric}=${p?.value} (threshold ${p?.threshold})`;
    default:
      return JSON.stringify(p);
  }
}

export function formatLogLine(entry: LogEntry): string {
  const msg = formatLogMessage(entry);
  return `#${entry.seq}\t${entry.ts}\t${entry.type}\t${msg}`;
}

export function logsToPlainText(entries: LogEntry[]): string {
  return entries.map(formatLogLine).join("\n");
}

export function logsToJson(entries: LogEntry[]): string {
  return JSON.stringify(entries, null, 2);
}

export function agentsToPlainText(
  agents: Record<string, AgentState>,
  pipeline: { id: string; name: string }[],
  currentAgent: string | null
): string {
  const lines: string[] = [
    `current_agent: ${currentAgent ?? "—"}`,
    "",
    "id\tstatus\tpass\tduration_ms\tname",
  ];
  const order = pipeline.length > 0 ? pipeline.map((s) => s.id) : Object.keys(agents);
  const seen = new Set<string>();
  for (const id of order) {
    seen.add(id);
    const a = agents[id];
    if (!a) {
      lines.push(`${id}\tpending\t-\t-\t${id}`);
      continue;
    }
    lines.push(
      `${a.id}\t${a.status}\t${a.passNumber}\t${a.durationMs ?? "-"}\t${a.name}`
    );
  }
  for (const id of Object.keys(agents)) {
    if (seen.has(id)) continue;
    const a = agents[id];
    lines.push(
      `${a.id}\t${a.status}\t${a.passNumber}\t${a.durationMs ?? "-"}\t${a.name}`
    );
  }
  return lines.join("\n");
}

export function agentsToJson(
  agents: Record<string, AgentState>,
  currentAgent: string | null
): string {
  return JSON.stringify({ current_agent: currentAgent, agents }, null, 2);
}
