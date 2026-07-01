import { useEffect, useRef, useCallback } from "react";
import { toast } from "sonner";
import { useSessionStore } from "@/stores/sessionStore";

const BACKOFF = [1000, 2000, 5000, 10000, 10000, 10000, 10000, 10000, 10000, 10000];

export function useAgentWebSocket(sessionId: string | null) {
  const ws = useRef<WebSocket | null>(null);
  const retryCount = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(true);

  const handleEnvelope = useSessionStore((s) => s.handleEnvelope);
  const setWsStatus = useSessionStore((s) => s.setWsStatus);

  const connect = useCallback(() => {
    if (!sessionId || !mounted.current) return;
    if (ws.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${protocol}://${window.location.host}/ws/sessions/${sessionId}`;

    setWsStatus("connecting");
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen = () => {
      retryCount.current = 0;
      setWsStatus("connected");
    };

    socket.onmessage = (evt) => {
      try {
        const envelope = JSON.parse(evt.data);
        if (envelope.type === "ping") {
          socket.send(JSON.stringify({ type: "pong" }));
          return;
        }
        handleEnvelope(envelope);

        // Toast for critical events
        if (envelope.type === "session_stuck") {
          toast.warning("Session appears stuck", {
            description: envelope.payload?.reason,
            duration: 10000,
          });
        }
        if (envelope.type === "error" && !envelope.payload?.recoverable) {
          toast.error("Agent error", { description: envelope.payload?.message });
        }
        if (envelope.type === "fallback_triggered") {
          toast.warning(`Fallback: ${envelope.payload?.layer}`, {
            description: envelope.payload?.message,
          });
        }
        if (envelope.type === "done") {
          const p = envelope.payload;
          toast.success(p?.is_partial ? "Completed (partial)" : "Specification complete!", {
            description: `${p?.artifacts_count} artifacts, ${p?.tasks_count} tasks`,
            duration: 10000,
          });
        }
      } catch {
        // ignore malformed frames
      }
    };

    socket.onerror = () => {
      setWsStatus("error");
    };

    socket.onclose = () => {
      if (!mounted.current) return;
      if (retryCount.current >= BACKOFF.length) {
        setWsStatus("error");
        toast.error("WebSocket disconnected. Retries exhausted. Use polling fallback.");
        return;
      }
      const delay = BACKOFF[retryCount.current++];
      setWsStatus("reconnecting");
      retryTimer.current = setTimeout(connect, delay);
    };
  }, [sessionId, handleEnvelope, setWsStatus]);

  useEffect(() => {
    mounted.current = true;
    connect();
    return () => {
      mounted.current = false;
      if (retryTimer.current) clearTimeout(retryTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg));
    }
  }, []);

  return { send };
}
