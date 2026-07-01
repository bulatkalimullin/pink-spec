import { useEffect, useState } from "react";

/** Tick ETA down between WS updates. */
export function useEtaCountdown(etaSec: number | null, etaUpdatedAt: number | null): number | null {
  const [displayEta, setDisplayEta] = useState<number | null>(etaSec);

  useEffect(() => {
    setDisplayEta(etaSec);
  }, [etaSec, etaUpdatedAt]);

  useEffect(() => {
    if (etaSec == null || etaUpdatedAt == null) return;

    const tick = () => {
      const elapsed = Math.floor((Date.now() - etaUpdatedAt) / 1000);
      setDisplayEta(Math.max(0, etaSec - elapsed));
    };

    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [etaSec, etaUpdatedAt]);

  return displayEta;
}
