import { useSessionStore } from "@/stores/sessionStore";
import { AlertTriangle, ArrowRight } from "lucide-react";

export default function FallbacksPanel() {
  const fallbacks = useSessionStore((s) => s.fallbacks);

  if (fallbacks.length === 0) {
    return <p className="px-3 py-2 text-xs text-zinc-600">No fallbacks triggered.</p>;
  }

  return (
    <div className="space-y-1 px-1 py-1">
      {fallbacks.map((f, i) => (
        <div key={i} className="flex gap-2 rounded p-2 bg-orange-900/10 border border-orange-800/30">
          <AlertTriangle className="h-3.5 w-3.5 text-orange-400 flex-shrink-0 mt-0.5" />
          <div className="min-w-0 space-y-0.5">
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className="font-semibold text-orange-300 uppercase">{f.layer}</span>
              <span className="text-zinc-600">/</span>
              <span className="text-zinc-400">{f.step}</span>
              {f.from && f.to && (
                <span className="flex items-center gap-1 text-zinc-500">
                  <span>{f.from}</span>
                  <ArrowRight className="h-2.5 w-2.5" />
                  <span className="text-zinc-300">{f.to}</span>
                </span>
              )}
            </div>
            <p className="text-xs text-orange-200/70">{f.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
