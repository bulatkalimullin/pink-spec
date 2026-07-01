import { useEffect, useRef } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { getSessionHealth, getSessionLogs } from "@/lib/api";

const POLL_INTERVAL_MS = 5000;
const STALE_EVENT_MS = 30_000;

export function useSessionPolling(sessionId: string | null) {
  const wsStatus = useSessionStore((s) => s.wsStatus);
  const lastEventAt = useSessionStore((s) => s.lastEventAt);
  const sessionStatus = useSessionStore((s) => s.sessionStatus);
  const handleEnvelope = useSessionStore((s) => s.handleEnvelope);
  const lastSeq = useRef(0);

  const shouldPoll =
    wsStatus !== "connected" ||
    (sessionStatus === "running" && Date.now() - lastEventAt > STALE_EVENT_MS);

  useEffect(() => {
    if (!sessionId || !shouldPoll) return;

    const poll = async () => {
      try {
        const health = await getSessionHealth(sessionId);
        if (health.status) {
          useSessionStore.setState({ sessionStatus: health.status });
        }
        if (health.stuck) {
          useSessionStore.setState({ isStuck: true });
        }

        const { logs } = await getSessionLogs(sessionId, lastSeq.current);
        for (const entry of logs as {
          seq: number;
          type: string;
          ts: string;
          session_id: string;
          payload: Record<string, unknown>;
        }[]) {
          if (entry.seq > lastSeq.current) {
            lastSeq.current = entry.seq;
          }
          handleEnvelope(entry);
        }
      } catch {
        /* ignore transient poll errors */
      }
    };

    void poll();
    const id = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [sessionId, shouldPoll, handleEnvelope]);
}
